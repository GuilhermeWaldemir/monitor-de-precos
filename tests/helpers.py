"""Constants and helpers imported by the tests."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

KABUM_URL = "https://www.kabum.com.br/produto/172366/memoria-ram-kingston-fury-beast-16gb-3200mhz-ddr4-cl16-preto-kf432c16bb1-16"
ML_URL = "https://www.mercadolivre.com.br/memoria-kingston-fury-beast-16gb-1x16gb-ddr4-3200mhz-c16-preto-kf432c16bb116/p/MLB18623867"
TERABYTE_URL = "https://www.terabyteshop.com.br/produto/19158/memoria-kingston-fury-beast-16gb-3200mhz-ddr4-cl16-preto-kf432c16bb116"
AMAZON_URL = "https://www.amazon.com.br/dp/B097K2MRS3"
MAGALU_URL = "https://www.magazineluiza.com.br/memoria-kingston-fury-beast-16gb-3200mhz-ddr4-cl16-preto-kf432c16bb1-16/p/gd5ak43hk3/in/pepc/"

RAM_CODE = "KF432C16BB1/16"

# Ids of the categories created by db.init_db, in order.
ELECTRONICS_ID, CLOTHING_ID, PERFUMES_ID = 1, 2, 3


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")
