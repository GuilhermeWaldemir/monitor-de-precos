"""Official Mercado Livre API (the legitimate way to read prices from that store).

The store blocks programs that read its pages, so instead of getting around the block the
project uses the API Mercado Livre itself offers. It works like this:

1. you create an application at developers.mercadolivre.com.br and put the App ID and the
   Secret Key in the .env;
2. in Configurações you click "Conectar", Mercado Livre asks you to authorize and sends
   back a short-lived `code`;
3. the site exchanges that code for an `access_token` (valid for 6 hours) and a
   `refresh_token`, both saved in the database;
4. from then on every read sends the token in the Authorization header. When the token is
   about to expire, the refresh token gets a new pair (the refresh token is single use, so
   the new one must be saved).
"""

import base64
import hashlib
import json
import logging
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode, urlparse

import requests

from monitor import db
from monitor.jsonld import ProductInfo

logger = logging.getLogger(__name__)

AUTHORIZATION_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
API_URL = "https://api.mercadolibre.com"
PROVIDER = "mercadolivre"
# "read" to read prices, "offline_access" to be able to renew the access without the user.
SCOPE = "offline_access read"

TIMEOUT_SECONDS = 20
# Renew a little before the token really expires, so a check never fails by a few seconds.
RENEW_BEFORE = timedelta(minutes=5)

# /p/MLB123 is a catalog page (many sellers); /MLB-123-name is one seller's listing.
CATALOG_PATTERN = re.compile(r"/p/(MLB\d+)", re.IGNORECASE)
ITEM_PATTERN = re.compile(r"(MLB-?\d+)", re.IGNORECASE)


class MercadoLivreError(Exception):
    """Something went wrong with the API. The message is shown to the user."""


@dataclass
class AppCredentials:
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_env(cls) -> "AppCredentials | None":
        import os

        client_id = os.environ.get("MONITOR_ML_CLIENT_ID", "").strip()
        client_secret = os.environ.get("MONITOR_ML_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            return None
        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=os.environ.get(
                "MONITOR_ML_REDIRECT_URI", "http://127.0.0.1:5000/mercadolivre/callback"
            ).strip(),
        )


# ---------- URLs ----------

def handles(url: str) -> bool:
    """True for Mercado Livre links (the only ones this module knows how to read)."""
    host = urlparse(url).hostname or ""
    return host.lower().endswith("mercadolivre.com.br")


def resource_from_url(url: str) -> tuple[str, str] | None:
    """("products", "MLB18623867") for a catalog page, ("items", "MLB123") for a listing."""
    if not handles(url):
        return None
    path = urlparse(url).path
    catalog = CATALOG_PATTERN.search(path)
    if catalog:
        return "products", catalog.group(1).upper()
    item = ITEM_PATTERN.search(path)
    if item:
        return "items", item.group(1).upper().replace("-", "")
    return None


def make_pkce_pair() -> tuple[str, str]:
    """PKCE: a random secret (verifier) and its SHA-256 fingerprint (challenge).

    The challenge goes in the authorization link; the verifier only goes in the token
    request, straight from this server. Someone who steals the `code` from the browser
    cannot use it, because they don't have the verifier.
    """
    verifier = secrets.token_urlsafe(64)  # 86 characters, within the 43-128 PKCE allows
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def authorization_url(credentials: AppCredentials, state: str, code_challenge: str | None = None) -> str:
    """Where to send the user to authorize the app.

    `state` is a random value we keep in the session and check when Mercado Livre sends the
    user back: it proves the answer belongs to the request this site started.
    """
    params = {
        "response_type": "code",
        "client_id": credentials.client_id,
        "redirect_uri": credentials.redirect_uri,
        "state": state,
        # Asking for offline_access is what makes Mercado Livre send a refresh token,
        # so the access renews itself instead of dying after 6 hours.
        "scope": SCOPE,
    }
    if code_challenge:
        params.update(code_challenge=code_challenge, code_challenge_method="S256")
    return f"{AUTHORIZATION_URL}?{urlencode(params)}"


def code_from_answer(answer: str) -> str:
    """The `code` from what the user pastes: the whole URL Mercado Livre opened, or the code itself."""
    answer = (answer or "").strip()
    if "code=" in answer:
        answer = answer.split("code=", 1)[1].split("&", 1)[0]
    if not answer or " " in answer:
        raise MercadoLivreError("Cole o código (ou a URL inteira) que o Mercado Livre devolveu.")
    return answer


# ---------- Tokens ----------

def connect(
    conn: sqlite3.Connection,
    credentials: AppCredentials,
    code: str,
    post_form=None,
    code_verifier: str | None = None,
) -> bool:
    """Exchange the authorization code for the tokens and save them.

    Returns True when the access renews itself, False when it lasts only 6 hours.
    """
    data = {
        "grant_type": "authorization_code",
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "code": code,
        "redirect_uri": credentials.redirect_uri,
    }
    if code_verifier:
        data["code_verifier"] = code_verifier
    return _save_tokens(conn, _post_token(data, post_form))


def disconnect(conn: sqlite3.Connection) -> None:
    db.delete_oauth_token(conn, PROVIDER)


def is_connected(conn: sqlite3.Connection) -> bool:
    return db.get_oauth_token(conn, PROVIDER) is not None


def access_token(conn: sqlite3.Connection, credentials: AppCredentials, post_form=None) -> str:
    """A token ready to use, renewing it when it is close to expiring."""
    token = db.get_oauth_token(conn, PROVIDER)
    if token is None:
        raise MercadoLivreError("Conecte a conta do Mercado Livre em Configurações.")

    expires_at = datetime.fromisoformat(token["expires_at"])
    if datetime.now() + RENEW_BEFORE < expires_at:
        return token["access_token"]

    if not token["refresh_token"]:
        raise MercadoLivreError(
            "O acesso ao Mercado Livre expirou. Conecte de novo em Configurações "
            "(ou ative a permissão offline_access na aplicação para renovar sozinho)."
        )

    answer = _post_token(
        {
            "grant_type": "refresh_token",
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "refresh_token": token["refresh_token"],
        },
        post_form,
    )
    _save_tokens(conn, answer)
    return answer["access_token"]


def _save_tokens(conn: sqlite3.Connection, answer: dict) -> bool:
    """Save the tokens. Returns True when the access can renew itself (refresh token came)."""
    if not isinstance(answer, dict):
        raise MercadoLivreError("Resposta inesperada do Mercado Livre ao pedir o token.")
    missing = [field for field in ("access_token", "expires_in") if not answer.get(field)]
    if missing:
        # Only field NAMES go in the message: the answer itself holds secrets.
        logger.warning("Mercado Livre token answer without %s; fields received: %s", missing, sorted(answer))
        raise MercadoLivreError(
            f"Resposta inesperada do Mercado Livre: faltou {', '.join(missing)} "
            f"(veio: {', '.join(sorted(answer)) or 'nada'})."
        )

    expires_at = datetime.now() + timedelta(seconds=int(answer["expires_in"]))
    # Mercado Livre only sends a refresh token when the app has the "offline_access"
    # permission. Without it the access still works, but only until it expires (6 hours).
    # The refresh token is single use: each renewal gives a new one, which must be saved.
    refresh_token = answer.get("refresh_token") or ""
    db.save_oauth_token(
        conn,
        PROVIDER,
        access_token=answer["access_token"],
        refresh_token=refresh_token,
        expires_at=expires_at.isoformat(timespec="seconds"),
    )
    return bool(refresh_token)


# ---------- Reading a product ----------

def read_product(
    conn: sqlite3.Connection,
    url: str,
    credentials: AppCredentials | None = None,
    get_json=None,
    post_form=None,
) -> ProductInfo:
    """Name, price, photo and stock of a Mercado Livre link, through the official API."""
    credentials = credentials or AppCredentials.from_env()
    if credentials is None:
        raise MercadoLivreError("Falta MONITOR_ML_CLIENT_ID e MONITOR_ML_CLIENT_SECRET no .env.")

    resource = resource_from_url(url)
    if resource is None:
        raise MercadoLivreError("Não consegui achar o código do anúncio (MLB...) nesse link.")

    kind, resource_id = resource
    token = access_token(conn, credentials, post_form)
    if kind == "items":
        return _product_info(_get_json(f"{API_URL}/items/{resource_id}", token, get_json))

    try:
        product = _get_json(f"{API_URL}/products/{resource_id}", token, get_json)
    except MercadoLivreError as error:
        if "não encontrado" in str(error):
            raise MercadoLivreError(
                "Esse produto não existe mais no catálogo do Mercado Livre. Troque o link por um atual."
            ) from None
        raise

    if not _price((product.get("buy_box_winner") or {}).get("price")):
        # No featured offer: look at every seller's offer for this catalog product.
        offers = _get_json(f"{API_URL}/products/{resource_id}/items", token, get_json)
        product = {**product, "buy_box_winner": _cheapest_new_offer(offers)}
    return _catalog_info(product)


def _product_info(item: dict) -> ProductInfo:
    """One seller's listing (/items/MLB...)."""
    price = _price(item.get("price"))
    if price is None:
        raise MercadoLivreError("O anúncio não tem preço (pode estar pausado ou encerrado).")
    pictures = item.get("pictures") or []
    return ProductInfo(
        name=str(item.get("title", "")).strip(),
        price=price,
        image_url=(pictures[0].get("secure_url") or pictures[0].get("url")) if pictures else item.get("thumbnail"),
        in_stock=item.get("status") == "active" and int(item.get("available_quantity") or 0) > 0,
        mpn=_attribute(item, "MPN", "PART_NUMBER", "SELLER_SKU"),
        gtin=_attribute(item, "GTIN", "EAN"),
    )


def _cheapest_new_offer(offers: dict) -> dict | None:
    """The cheapest offer among the sellers of a catalog product, skipping used items.

    `/products/{id}/items` lists every seller; the comparator wants the lowest price for
    the same NEW product (a used one would be an unfair comparison).
    """
    candidates = [
        offer for offer in (offers or {}).get("results") or []
        if _price(offer.get("price")) and offer.get("condition", "new") == "new"
    ]
    return min(candidates, key=lambda offer: _price(offer["price"]), default=None)


def _catalog_info(product: dict) -> ProductInfo:
    """Catalog page (/products/MLB...): the offer is `buy_box_winner` (or the cheapest seller)."""
    winner = product.get("buy_box_winner") or {}
    price = _price(winner.get("price"))
    if price is None:
        raise MercadoLivreError("Esse produto do catálogo está sem nenhuma oferta à venda no momento.")
    pictures = product.get("pictures") or []
    # Some answers hide the quantity (None): unknown stock, not "out of stock".
    quantity = winner.get("available_quantity")
    return ProductInfo(
        name=str(product.get("name", "")).strip(),
        price=price,
        image_url=(pictures[0].get("secure_url") or pictures[0].get("url")) if pictures else None,
        in_stock=None if quantity is None else int(quantity) > 0,
        mpn=_attribute(product, "MPN", "PART_NUMBER"),
        gtin=_attribute(product, "GTIN", "EAN"),
    )


def _price(value) -> Decimal | None:
    if value is None:
        return None
    price = Decimal(str(value))  # str() first: the JSON number must never become a float
    return price.quantize(Decimal("0.01")) if price > 0 else None


def _attribute(data: dict, *ids: str) -> str | None:
    """Value of the first attribute with one of these ids (GTIN, MPN...)."""
    wanted = {name.upper() for name in ids}
    for attribute in data.get("attributes") or []:
        if str(attribute.get("id", "")).upper() in wanted:
            value = attribute.get("value_name") or attribute.get("value_id")
            if value:
                return str(value).strip()
    return None


# ---------- HTTP (replaced by fakes in the tests) ----------

def _get_json(url: str, token: str, get_json=None) -> dict:
    if get_json is not None:
        return get_json(url, token)
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise MercadoLivreError(f"Não consegui falar com a API: {error.__class__.__name__}.") from None
    if response.status_code == 404:
        raise MercadoLivreError("Anúncio não encontrado na API (pode ter sido removido).")
    if response.status_code in (401, 403):
        raise MercadoLivreError("A API recusou o acesso. Conecte a conta do Mercado Livre de novo.")
    if response.status_code != 200:
        raise MercadoLivreError(f"A API respondeu com erro HTTP {response.status_code}.")
    return response.json(parse_float=Decimal)  # prices as Decimal, never float


def _post_token(data: dict, post_form=None) -> dict:
    if post_form is not None:
        return post_form(TOKEN_URL, data)
    try:
        response = requests.post(
            TOKEN_URL,
            data=data,
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as error:
        raise MercadoLivreError(f"Não consegui falar com a API: {error.__class__.__name__}.") from None
    if response.status_code != 200:
        raise MercadoLivreError(token_error_message(response.status_code, response.text))
    return response.json(parse_float=Decimal)


def token_error_message(status_code: int, body: str) -> str:
    """Turn Mercado Livre's error answer into a message that says what to do."""
    try:
        answer = json.loads(body)
        error, detail = str(answer.get("error", "")), str(answer.get("message", ""))
    except (ValueError, AttributeError):
        error, detail = "", body[:200]
    logger.warning("Mercado Livre token error %s: %s %s", status_code, error, detail)

    if error == "invalid_client":
        hint = "O App ID ou a Secret Key não conferem com a aplicação no portal do Mercado Livre."
    elif "redirect" in detail.lower():
        hint = "A URL de retorno do .env não é idêntica à cadastrada na aplicação."
    elif error == "invalid_grant":
        hint = ("O código expirou (vale poucos minutos) ou já foi usado. "
                "Clique em Conectar de novo e cole a URL logo em seguida.")
    else:
        hint = "Confira o App ID, a Secret Key e a URL de retorno."
    return f"O Mercado Livre recusou a autorização ({error or status_code}: {detail}). {hint}"
