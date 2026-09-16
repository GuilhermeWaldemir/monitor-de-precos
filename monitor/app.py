"""Web site (Flask). Run with: flask --app monitor.app run --debug

Flask finds the create_app() function below by itself.
"""

import os
import secrets
from contextlib import closing
from datetime import datetime
from decimal import Decimal

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for

from monitor import alerts, auth, checker, compare, db, emailer, history, mercadolivre
from monitor.config import load_env_file
from monitor.capture import bookmarklet_href, read_captured
from monitor.fetcher import fetch_html
from monitor.matching import code_matches
from monitor.stores import link_key
from monitor.icons import CATEGORY_ICONS, DEFAULT_CATEGORY_ICON
from monitor.prices import format_brl, format_percent, parse_brl_price
from monitor.search import search_products
from monitor.settings import (
    CHOICES,
    FONT_DESCRIPTIONS,
    FONT_LABELS,
    THEME_DESCRIPTIONS,
    THEME_LABELS,
    load_settings,
    save_settings,
)
from monitor.similar import find_similar

# One row per radio option on the settings page: value, label and short description.
THEME_OPTIONS = [
    {"value": value, "label": THEME_LABELS[value], "description": THEME_DESCRIPTIONS[value]}
    for value in CHOICES["theme"]
]
FONT_OPTIONS = [
    {"value": value, "label": FONT_LABELS[value], "description": FONT_DESCRIPTIONS[value]}
    for value in CHOICES["font"]
]

# Anyone can browse the site. Changing anything needs an account (see require_login below).
PUBLIC_ENDPOINTS = {"static", "login", "signup"}
# Pages that only exist to change data, so they need an account even being a GET.
PAGES_THAT_NEED_LOGIN = {
    "new_product", "edit_product", "capture_page", "mercadolivre_connect", "mercadolivre_callback",
}


def create_app(db_path=db.DEFAULT_DB_PATH, fetch=None, send_email=None) -> Flask:
    """Build the app. Tests pass a temporary database, a fake `fetch` and a fake `send_email`."""
    load_env_file()  # passwords and SMTP settings live in .env, outside Git
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-secret")
    app.config["DB_PATH"] = db_path
    fetch = fetch or fetch_html
    send_email = send_email or emailer.send_email

    with closing(db.connect(db_path)) as conn:  # closing() closes the connection at the end
        db.init_db(conn)

    def get_conn():
        # One connection per request, closed at the end (teardown below).
        if "conn" not in g:
            g.conn = db.connect(app.config["DB_PATH"])
        return g.conn

    @app.teardown_appcontext
    def close_conn(_error):
        conn = g.pop("conn", None)
        if conn is not None:
            conn.close()

    # ---------- Accounts ----------

    def current_user():
        """The logged-in user (a row) or None. Read once per request."""
        if "user" not in g:
            user_id = session.get("user_id")
            g.user = db.get_user(get_conn(), user_id) if user_id else None
        return g.user

    @app.before_request
    def require_login_to_change_things():
        """Visitors can look around; everything that changes data needs an account."""
        if current_user() is not None or request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if request.method == "POST" or request.endpoint in PAGES_THAT_NEED_LOGIN:
            flash("Entre na sua conta para fazer isso.", "error")
            return redirect(url_for("login", next=request.path))
        return None

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if request.method == "GET":
            return render_template("auth.html", mode="signup", form={})
        try:
            user_id = auth.register(
                get_conn(),
                request.form.get("email", ""),
                request.form.get("password", ""),
                request.form.get("password_confirm", ""),
            )
        except ValueError as error:
            return render_template("auth.html", mode="signup", form=request.form, error=str(error)), 400

        _start_session(user_id)
        flash("Conta criada. Os alertas de preço vão para esse e-mail.", "ok")
        return redirect(url_for("index"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        next_path = auth.safe_next_path(request.values.get("next"))
        if request.method == "GET":
            return render_template("auth.html", mode="login", form={}, next_path=next_path)

        user = auth.authenticate(get_conn(), request.form.get("email", ""), request.form.get("password"))
        if user is None:
            return render_template(
                "auth.html", mode="login", form=request.form, next_path=next_path,
                error="E-mail ou senha incorretos.",
            ), 400

        _start_session(user["id"])
        flash(f"Bem-vindo de volta, {user['email']}.", "ok")
        return redirect(next_path or url_for("index"))

    @app.post("/logout")
    def logout():
        session.clear()
        g.pop("user", None)
        flash("Você saiu da sua conta.", "ok")
        return redirect(url_for("index"))

    def _start_session(user_id: int) -> None:
        # clear() first: a brand new session id for the new login (avoids session fixation).
        session.clear()
        session["user_id"] = user_id
        g.pop("user", None)

    # ---------- Template helpers ----------

    @app.context_processor
    def sidebar_data():
        """Variables available in every template (the sidebar needs them on all pages)."""
        categories = db.list_categories_with_counts(get_conn())
        return {
            "categories": categories,
            "total_products": sum(c["product_count"] for c in categories),
            "settings": load_settings(get_conn()),
            "category_icons": CATEGORY_ICONS,  # for the icon picker (sidebar and category page)
            "current_user": current_user(),
        }

    @app.template_filter("brl")
    def brl_filter(value) -> str:
        return format_brl(Decimal(str(value)))

    @app.template_filter("when")
    def when_filter(value: datetime) -> str:
        return value.strftime("%d/%m às %H:%M")

    @app.template_filter("percent")
    def percent_filter(value) -> str:
        return format_percent(value)

    # ---------- Product grid ----------

    def render_grid(products, **context):
        """The product grid (home, category, search), with each product's best price for the slider."""
        prices = compare.best_prices(get_conn(), products)
        return render_template(
            "index.html",
            products=products,
            best_prices=prices,
            price_range=compare.price_range(prices),
            **context,
        )

    @app.get("/")
    def index():
        return render_grid(db.list_products(get_conn()), heading="Todos os produtos", category=None)

    @app.get("/categories/<int:category_id>")
    def category_page(category_id: int):
        category = _get_or_404(db.get_category, category_id)
        return render_grid(
            db.list_products(get_conn(), category_id),
            heading=category["name"],
            category=category,
            active_category_id=category_id,
        )

    @app.get("/search")
    def search():
        query = request.args.get("q", "").strip()
        if not query:
            return redirect(url_for("index"))
        return render_grid(
            search_products(get_conn(), query),
            heading=f"Resultados para “{query}”",
            category=None,
            search_query=query,
        )

    # ---------- Categories ----------

    @app.post("/categories")
    def create_category():
        try:
            category_id = db.create_category(
                get_conn(),
                request.form.get("name", ""),
                request.form.get("icon", DEFAULT_CATEGORY_ICON),
            )
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("index"))
        flash("Categoria criada.", "ok")
        return redirect(url_for("category_page", category_id=category_id))

    @app.post("/categories/<int:category_id>/edit")
    def edit_category(category_id: int):
        _get_or_404(db.get_category, category_id)
        try:
            db.update_category(
                get_conn(),
                category_id,
                name=request.form.get("name", ""),
                icon=request.form.get("icon", DEFAULT_CATEGORY_ICON),
            )
        except ValueError as error:
            flash(str(error), "error")
        else:
            flash("Categoria atualizada.", "ok")
        return redirect(url_for("category_page", category_id=category_id))

    @app.post("/categories/<int:category_id>/delete")
    def delete_category(category_id: int):
        category = _get_or_404(db.get_category, category_id)
        try:
            db.delete_category(get_conn(), category_id)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("category_page", category_id=category_id))
        flash(f"Categoria “{category['name']}” excluída.", "ok")
        return redirect(url_for("index"))

    # ---------- Create / edit products ----------

    @app.get("/products/new")
    def new_product():
        category_id = request.args.get("category", type=int)
        # Fields can come pre-filled in the URL (used by "Cadastrar novo produto" on the capture page).
        form = {
            "category_id": category_id,
            "name": request.args.get("name", ""),
            "code": request.args.get("code", ""),
            "links": request.args.get("links", ""),
        }
        return render_template("product_form.html", form=form, product=None, active_category_id=category_id)

    @app.post("/products")
    def create_product():
        conn = get_conn()
        form = request.form
        category_id = form.get("category_id", type=int)

        def form_again(status=400, **extra):
            return render_template("product_form.html", form=form, product=None, **extra), status

        duplicate = db.find_product_by_code(conn, form.get("code"))
        if duplicate is not None:
            return form_again(error="Você já cadastrou um produto com esse código.", duplicate=duplicate)

        if form.get("name", "").strip() and not form.get("confirm"):
            similar = find_similar(conn, form["name"], form.get("code"), category_id=category_id)
            if similar:
                return form_again(status=200, similar=similar)

        try:
            product_id = db.create_product(
                conn,
                name=form.get("name", ""),
                category_id=category_id,
                urls=form.get("links", "").splitlines(),
                manufacturer_code=form.get("code"),
            )
        except ValueError as error:
            return form_again(error=str(error))

        _flash_results(checker.check_product(conn, product_id, fetch=fetch))
        _announce_price_drop(product_id)
        return redirect(url_for("product_page", product_id=product_id))

    @app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
    def edit_product(product_id: int):
        conn = get_conn()
        product = _get_or_404(db.get_product, product_id)

        if request.method == "GET":
            form = {"name": product["name"], "code": product["manufacturer_code"] or "", "category_id": product["category_id"]}
            return render_template(
                "product_form.html", form=form, product=product, active_category_id=product["category_id"]
            )

        form = request.form
        duplicate = db.find_product_by_code(conn, form.get("code"), exclude_id=product_id)
        if duplicate is not None:
            return render_template(
                "product_form.html", form=form, product=product,
                error="Outro produto já usa esse código.", duplicate=duplicate,
            ), 400
        try:
            db.update_product(
                conn,
                product_id,
                name=form.get("name", ""),
                category_id=form.get("category_id", type=int),
                manufacturer_code=form.get("code"),
            )
        except ValueError as error:
            return render_template("product_form.html", form=form, product=product, error=str(error)), 400

        flash("Produto atualizado.", "ok")
        return redirect(url_for("product_page", product_id=product_id))

    # ---------- Product page ----------

    @app.get("/products/<int:product_id>")
    def product_page(product_id: int):
        conn = get_conn()
        product = _get_or_404(db.get_product, product_id)
        return render_template(
            "product.html",
            product=compare.compare_product(conn, product),
            similar=find_similar(
                conn, product["name"], product["manufacturer_code"],
                category_id=product["category_id"], exclude_id=product_id,
            ),
            chart=history.chart_data(db.price_history(conn, product_id)),
            drops=alerts.recent_drops(conn, product),
            active_category_id=product["category_id"],
        )

    @app.post("/products/<int:product_id>/check")
    def check_product(product_id: int):
        _get_or_404(db.get_product, product_id)
        _flash_results(checker.check_product(get_conn(), product_id, fetch=fetch))
        _announce_price_drop(product_id)
        return redirect(url_for("product_page", product_id=product_id))

    @app.post("/products/<int:product_id>/delete")
    def delete_product(product_id: int):
        product = _get_or_404(db.get_product, product_id)
        db.delete_product(get_conn(), product_id)
        flash(f"“{product['name']}” foi removido.", "ok")
        return redirect(url_for("category_page", category_id=product["category_id"]))

    # ---------- Sources (links) ----------

    @app.post("/products/<int:product_id>/links")
    def add_link(product_id: int):
        conn = get_conn()
        _get_or_404(db.get_product, product_id)
        try:
            link_id = db.add_link(conn, product_id, request.form.get("url", ""))
        except ValueError as error:
            flash(str(error), "error")
        else:
            _flash_results([checker.check_link(conn, link_id, fetch=fetch)])
            _announce_price_drop(product_id)
        return redirect(url_for("product_page", product_id=product_id, _anchor="sources"))

    @app.post("/links/<int:link_id>/delete")
    def delete_link(link_id: int):
        link = _get_or_404(db.get_link, link_id)
        db.delete_link(get_conn(), link_id)
        flash(f"Fonte {link['store']} removida.", "ok")
        return redirect(url_for("product_page", product_id=link["product_id"], _anchor="sources"))

    @app.post("/links/<int:link_id>/manual-price")
    def manual_price(link_id: int):
        conn = get_conn()
        link = _get_or_404(db.get_link, link_id)
        try:
            price = parse_brl_price(request.form.get("price", ""))
        except ValueError:
            flash("Preço inválido. Use o formato 1.299,90.", "error")
        else:
            db.add_price_check(conn, link_id, source="manual", price=price)
            flash(f"Preço da {link['store']} salvo: {format_brl(price)}.", "ok")
            _announce_price_drop(link["product_id"])
        return redirect(url_for("product_page", product_id=link["product_id"], _anchor="sources"))

    # ---------- "Capturar preço" bookmarklet ----------

    @app.get("/capture")
    def capture_page():
        """Shows what the bookmarklet read from the store page. Saves nothing (GET)."""
        return render_capture(request.args)

    @app.post("/capture")
    def save_capture():
        conn = get_conn()
        form = request.form
        try:
            page = read_captured(form)
        except ValueError as error:
            return render_capture(form, error=str(error))
        try:
            price = parse_brl_price(form.get("price", ""))
        except ValueError:
            return render_capture(form, error="Informe um preço válido, como 929,99.")

        link = db.get_link(conn, form.get("link_id", type=int) or 0)
        if link is not None:
            # The chosen link must really be the page that was captured.
            if link_key(link["url"]) != link_key(page.url):
                return render_capture(form, error="Esse link não corresponde à página capturada.")
            link_id = link["id"]
        else:
            product = db.get_product(conn, form.get("product_id", type=int) or 0)
            if product is None:
                return render_capture(form, error="Escolha o produto a que essa página pertence.")
            # Reuse the product's link to this page if it already has one (maybe written differently).
            same_page = [row for row in db.find_links_for_url(conn, page.url) if row["product_id"] == product["id"]]
            link_id = same_page[0]["id"] if same_page else db.add_link(conn, product["id"], page.url)
            link = db.get_link(conn, link_id)

        db.add_price_check(
            conn, link_id, source="capture", price=price,
            page_title=page.name or None, page_code=page.mpn, page_gtin=page.gtin,
        )
        if page.image_url:
            db.set_image_if_missing(conn, link["product_id"], page.image_url)
        flash(f"Preço da {link['store']} capturado: {format_brl(price)}.", "ok")
        _announce_price_drop(link["product_id"])
        return redirect(url_for("product_page", product_id=link["product_id"], _anchor="sources"))

    def render_capture(values, error=None):
        conn = get_conn()
        try:
            page = read_captured(values)
        except ValueError:
            return render_template(
                "capture.html", page=None, error="O favorito não enviou um link de produto válido."
            ), 400
        matches = [
            {"link": link, "code_matches": code_matches(link["manufacturer_code"], page.mpn, page.gtin, page.name)}
            for link in db.find_links_for_url(conn, page.url)
        ]
        return render_template(
            "capture.html",
            page=page,
            matches=matches,
            products=db.list_products(conn),
            typed_price=values.get("price", ""),
            error=error,
        ), 400 if error else 200

    # ---------- Mercado Livre (official API) ----------

    @app.get("/mercadolivre/connect")
    def mercadolivre_connect():
        """Sends the user to Mercado Livre to authorize this app."""
        credentials = mercadolivre.AppCredentials.from_env()
        if credentials is None:
            flash("Falta MONITOR_ML_CLIENT_ID e MONITOR_ML_CLIENT_SECRET no .env.", "error")
            return redirect(url_for("settings", _anchor="mercado-livre"))

        # Random value kept in the session: proves the answer belongs to this request.
        state = secrets.token_urlsafe(16)
        # PKCE: the verifier stays on this server; only its fingerprint goes in the link.
        code_verifier, code_challenge = mercadolivre.make_pkce_pair()
        session["ml_state"] = state
        session["ml_code_verifier"] = code_verifier
        return redirect(mercadolivre.authorization_url(credentials, state, code_challenge))

    @app.get("/mercadolivre/callback")
    def mercadolivre_callback():
        """Where Mercado Livre sends the user back, with the authorization code."""
        expected_state = session.pop("ml_state", None)
        if not expected_state or request.args.get("state") != expected_state:
            flash("Autorização não confere com o pedido feito aqui. Tente conectar de novo.", "error")
            return redirect(url_for("settings", _anchor="mercado-livre"))
        return _finish_ml_connection(request.args.get("code", ""))

    @app.post("/mercadolivre/code")
    def mercadolivre_code():
        """Manual way: the user pastes the URL (or the code) Mercado Livre showed."""
        try:
            code = mercadolivre.code_from_answer(request.form.get("answer", ""))
        except mercadolivre.MercadoLivreError as error:
            flash(str(error), "error")
            return redirect(url_for("settings", _anchor="mercado-livre"))
        return _finish_ml_connection(code)

    @app.post("/mercadolivre/disconnect")
    def mercadolivre_disconnect():
        mercadolivre.disconnect(get_conn())
        flash("Conta do Mercado Livre desconectada.", "ok")
        return redirect(url_for("settings", _anchor="mercado-livre"))

    def _finish_ml_connection(code: str):
        credentials = mercadolivre.AppCredentials.from_env()
        try:
            mercadolivre.connect(
                get_conn(),
                credentials,
                mercadolivre.code_from_answer(code),
                # The same browser session that clicked "Conectar" holds the PKCE verifier.
                code_verifier=session.get("ml_code_verifier"),
            )
        except mercadolivre.MercadoLivreError as error:
            flash(str(error), "error")
        else:
            session.pop("ml_code_verifier", None)
            flash("Mercado Livre conectado. Os preços passam a vir da API oficial.", "ok")
        return redirect(url_for("settings", _anchor="mercado-livre"))

    # ---------- Settings ----------

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        conn = get_conn()
        if request.method == "POST":
            # Only keys actually present in the form are saved, so a form that only has
            # a "theme" field (or a future page missing a "font" field) never wipes the
            # other setting's saved value.
            # On/off switches send a hidden "off" first and the checkbox's "on" after it
            # (an unchecked checkbox sends nothing), so the LAST value of each key wins.
            values = {key: request.form.getlist(key)[-1] for key in CHOICES if key in request.form}
            try:
                save_settings(conn, values)
            except ValueError as error:
                return render_settings(error=str(error)), 400
            flash("Configurações salvas.", "ok")
            return redirect(url_for("settings"))
        return render_settings()

    @app.post("/settings/test-email")
    def test_email():
        """Sends one e-mail to the logged-in account, to check the .env settings."""
        user = current_user()
        try:
            send_email(
                user["email"],
                "Monitor de Preços: e-mail de teste",
                "Se você recebeu este e-mail, os alertas de queda de preço vão chegar aqui.",
            )
        except emailer.EmailError as error:
            flash(str(error), "error")
        else:
            flash(f"E-mail de teste enviado para {user['email']}.", "ok")
        return redirect(url_for("settings", _anchor="alertas"))

    def render_settings(**context):
        smtp = emailer.SmtpConfig.from_env()
        return render_template(
            "settings.html",
            theme_options=THEME_OPTIONS,
            font_options=FONT_OPTIONS,
            smtp_config=smtp,
            ml_credentials=mercadolivre.AppCredentials.from_env(),
            ml_token=db.get_oauth_token(get_conn(), mercadolivre.PROVIDER),
            # The bookmarklet must point back to this site, wherever it is running.
            bookmarklet_href=bookmarklet_href(request.url_root),
            **context,
        )

    # ---------- Helpers ----------

    def _get_or_404(getter, item_id: int):
        item = getter(get_conn(), item_id)
        if item is None:
            abort(404)
        return item

    def _announce_price_drop(product_id: int) -> None:
        """After new prices are saved: warn when the best price dropped 4% or more."""
        conn = get_conn()
        drop = alerts.check_product_for_drop(conn, product_id)
        if drop is None:
            return

        flash(
            f"Caiu {drop.percent_text}! {drop.product_name}: "
            f"{format_brl(drop.old_price)} → {format_brl(drop.new_price)} na {drop.store}.",
            "drop",
        )
        _email_price_drop(conn, drop)

    def _email_price_drop(conn, drop) -> None:
        """E-mail every account about the drop. A failure here never breaks the page."""
        recipients = db.list_user_emails(conn)
        if not recipients:
            return

        subject, body = alerts.drop_email(
            drop, url_for("product_page", product_id=drop.product_id, _external=True)
        )
        sent_to = []
        for address in recipients:
            try:
                send_email(address, subject, body)
            except emailer.EmailError as error:
                flash(f"Aviso não enviado para {address}. {error}", "error")
            else:
                sent_to.append(address)

        if sent_to:
            db.mark_alert_emailed(conn, drop.alert_id)
            flash(f"Aviso enviado para {', '.join(sent_to)}.", "ok")

    def _flash_results(results) -> None:
        for result in results:
            flash(f"{result.store}: {result.message}", "ok" if result.ok else "error")

    return app
