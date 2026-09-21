"""Modo demonstração: o site no ar, para quem só quer ver como ele funciona.

Dois motivos para existir:

1. Um servidor na nuvem é bloqueado pelas lojas (o IP é de datacenter), então lá o site
   não conseguiria ler preço nenhum e a demonstração ficaria vazia.
2. O site publicado é aberto: sem isso, qualquer pessoa poderia apagar os produtos.

Por isso, com MONITOR_DEMO ligado: o banco começa com dados de **exemplo** e todo POST é
recusado. Os preços daqui são **inventados** — copiar os preços reais das lojas para um
site público seria redistribuir dados delas, o que o projeto não faz (veja o CLAUDE.md).
"""

import os
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal

from monitor import db

VARIABLE = "MONITOR_DEMO"
ON_VALUES = {"1", "true", "sim", "on", "yes"}

# Uma verificação a cada 3 dias, terminando hoje: dá cinco pontos no gráfico.
HISTORY_DAYS = (12, 9, 6, 3, 0)

# Produtos de exemplo. `prices` anda junto com HISTORY_DAYS; None = a verificação falhou.
EXAMPLE_PRODUCTS = [
    {
        "category": "Eletrônicos",
        "name": "Memória RAM 16GB DDR4 3200MHz (exemplo)",
        "code": "DEMO-RAM16-3200",
        "offers": [
            {
                "url": "https://www.kabum.com.br/produto/000001/memoria-ram-16gb-exemplo",
                "prices": ["489.90", "489.90", "469.90", "469.90", "429.90"],
            },
            {
                "url": "https://www.terabyteshop.com.br/produto/00001/memoria-ram-16gb-exemplo",
                "prices": ["499.00", "499.00", "499.00", "479.00", "479.00"],
            },
            {
                "url": "https://www.amazon.com.br/dp/DEMO000001",
                "prices": ["512.30", "505.00", "505.00", "498.70", "498.70"],
            },
        ],
        # A última queda (469,90 -> 429,90) passa dos 4% e vira um alerta por e-mail.
        "alert": {"old": "469.90", "new": "429.90", "store": "KaBuM!"},
    },
    {
        "category": "Eletrônicos",
        "name": "Teclado mecânico sem fio (exemplo)",
        "code": "DEMO-TEC-01",
        "offers": [
            {
                "url": "https://www.kabum.com.br/produto/000002/teclado-mecanico-exemplo",
                "prices": ["319.00", "319.00", "329.00", "329.00", "329.00"],
            },
            {
                "url": "https://www.magazineluiza.com.br/teclado-exemplo/p/demo002/in/tecl/",
                # A Magazine Luiza bloqueia a leitura automática: aqui o preço é informado à mão.
                "prices": ["334.90", None, "334.90", None, "324.90"],
                "source": "manual",
                "error": "A loja bloqueou a leitura automática (403).",
            },
        ],
    },
    {
        "category": "Perfumes",
        "name": "Perfume floral 100ml (exemplo)",
        "code": "7891234567895",  # um EAN de exemplo (código de barras)
        "offers": [
            {
                "url": "https://www.amazon.com.br/dp/DEMO000003",
                "prices": ["259.90", "259.90", "249.90", "249.90", "249.90"],
            },
            {
                "url": "https://www.mercadolivre.com.br/perfume-floral-exemplo/p/MLB0000003",
                # Mais barato, mas esgotado: por isso não vira o melhor preço.
                "prices": ["219.90", "219.90", "219.90", "219.90", "219.90"],
                "in_stock": False,
            },
        ],
    },
    {
        "category": "Vestuário",
        "name": "Camiseta básica de algodão (exemplo)",
        "code": None,  # sem código: as ofertas ficam "não confirmadas"
        "offers": [
            {
                "url": "https://www.amazon.com.br/dp/DEMO000004",
                "prices": ["79.90", "79.90", "79.90", "69.90", "69.90"],
            },
            {
                "url": "https://www.magazineluiza.com.br/camiseta-exemplo/p/demo004/mo/cami/",
                "prices": ["74.90", "74.90", "74.90", "74.90", "74.90"],
                "source": "manual",
            },
        ],
    },
]


def is_on(environ: dict | None = None) -> bool:
    """O modo demonstração está ligado? (variável MONITOR_DEMO no ambiente)"""
    value = (environ if environ is not None else os.environ).get(VARIABLE, "")
    return value.strip().lower() in ON_VALUES


def _date_days_ago(days: int) -> str:
    """No mesmo formato que db.now() grava, para as consultas ordenarem certo."""
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def fill_if_empty(conn: sqlite3.Connection) -> bool:
    """Cadastra os produtos de exemplo num banco vazio. Devolve se cadastrou algo.

    Rodar de novo não duplica nada: se já existe produto, não faz nada. Isso importa
    porque o servidor recria o banco a cada partida (o disco da nuvem é descartável).
    """
    if db.list_products(conn):
        return False

    categories = {row["name"]: row["id"] for row in db.list_categories_with_counts(conn)}
    for example in EXAMPLE_PRODUCTS:
        offers = example["offers"]
        product_id = db.create_product(
            conn,
            name=example["name"],
            category_id=categories[example["category"]],
            urls=[offer["url"] for offer in offers],
            manufacturer_code=example["code"],
        )
        # list_links devolve na ordem em que foram criados, igual à ordem de `offers`.
        for link, offer in zip(db.list_links(conn, product_id), offers):
            _add_history(conn, link, offer, example)

        alert = example.get("alert")
        if alert:
            db.set_alert_reference(conn, product_id, Decimal(alert["new"]))
            alert_id = db.add_price_alert(
                conn,
                product_id,
                old_price=Decimal(alert["old"]),
                new_price=Decimal(alert["new"]),
                store=alert["store"],
            )
            db.mark_alert_emailed(conn, alert_id)  # na demonstração o aviso já "foi enviado"
    return True


def _add_history(conn: sqlite3.Connection, link: sqlite3.Row, offer: dict, example: dict) -> None:
    for days, price in zip(HISTORY_DAYS, offer["prices"]):
        failed = price is None
        db.add_price_check(
            conn,
            link["id"],
            source=offer.get("source", "auto"),
            price=None if failed else Decimal(price),
            in_stock=None if failed else offer.get("in_stock", True),
            page_title=None if failed else example["name"],
            page_code=None if failed else example["code"],
            error=offer.get("error") if failed else None,
            checked_at=_date_days_ago(days),
        )
