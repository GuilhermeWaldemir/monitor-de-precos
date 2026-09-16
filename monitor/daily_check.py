"""Daily price check, run without the site being open.

The Windows Task Scheduler calls scripts/verificacao-diaria.cmd every day at 12:30, which
runs this module. It checks every product, applies the price drop rule (monitor/alerts.py),
e-mails the drops and writes what happened to data/verificacao-diaria.log.

Run by hand with:  py -m monitor.daily_check
"""

import logging
import os
import sys
import time
from contextlib import closing
from pathlib import Path

from monitor import alerts, checker, db, emailer
from monitor.config import load_env_file
from monitor.fetcher import fetch_html

LOG_PATH = Path("data") / "verificacao-diaria.log"
# Small pause between products: a scheduled run must stay gentle with the stores.
PAUSE_SECONDS = 3
DEFAULT_SITE_URL = "http://127.0.0.1:5000"

logger = logging.getLogger("monitor.daily_check")


def run(conn, fetch=None, send_email=None, site_url: str = DEFAULT_SITE_URL, pause: float = PAUSE_SECONDS) -> dict:
    """Check every product once. Returns a small summary (also used by the tests)."""
    send_email = send_email or emailer.send_email
    fetch = fetch or fetch_html
    summary = {"products": 0, "prices": 0, "failures": 0, "drops": 0, "emails": 0}

    products = db.list_products(conn)
    logger.info("Verificando %d produto(s).", len(products))

    for position, product in enumerate(products):
        if position and pause:
            time.sleep(pause)

        summary["products"] += 1
        results = _check_one(conn, product, fetch)
        summary["prices"] += sum(1 for result in results if result.ok)
        summary["failures"] += sum(1 for result in results if not result.ok)

        drop = alerts.check_product_for_drop(conn, product["id"])
        if drop is None:
            continue
        summary["drops"] += 1
        logger.info(
            "Queda de %s em %s: %s -> %s (%s)",
            drop.percent_text, drop.product_name, drop.old_price, drop.new_price, drop.store,
        )
        summary["emails"] += _email_drop(conn, drop, send_email, site_url)

    logger.info(
        "Fim: %(products)d produtos, %(prices)d preços lidos, %(failures)d falhas, "
        "%(drops)d quedas, %(emails)d e-mails.", summary,
    )
    return summary


def _check_one(conn, product, fetch) -> list:
    """One product's links. A crash here must not stop the other products."""
    try:
        results = checker.check_product(conn, product["id"], fetch=fetch)
    except Exception:
        logger.exception("Erro inesperado ao verificar %s", product["name"])
        return []

    for result in results:
        level = logging.INFO if result.ok else logging.WARNING
        logger.log(level, "%s - %s: %s", product["name"], result.store, result.message)
    return results


def _email_drop(conn, drop, send_email, site_url: str) -> int:
    """E-mail every account about the drop. Returns how many messages went out."""
    recipients = db.list_user_emails(conn)
    if not recipients:
        logger.warning("Ninguém cadastrado para receber o aviso.")
        return 0

    subject, body = alerts.drop_email(drop, f"{site_url.rstrip('/')}/products/{drop.product_id}")
    sent = 0
    for address in recipients:
        try:
            send_email(address, subject, body)
        except emailer.EmailError as error:
            logger.error("Não enviei para %s: %s", address, error)
        else:
            sent += 1
            logger.info("Aviso enviado para %s.", address)

    if sent:
        db.mark_alert_emailed(conn, drop.alert_id)
    return sent


def _setup_logging() -> None:
    """Write to the log file and to the screen (handy when running it by hand)."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # The Windows console is not UTF-8 by default, and accents would come out wrong.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
        handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )


def main() -> int:
    load_env_file()
    _setup_logging()
    try:
        with closing(db.connect()) as conn:
            db.init_db(conn)
            run(conn, site_url=os.environ.get("MONITOR_SITE_URL", DEFAULT_SITE_URL))
    except Exception:
        logger.exception("A verificação agendada falhou.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
