import json
from decimal import Decimal

from bs4 import BeautifulSoup


def parse_price(html: str) -> Decimal:

    soup = BeautifulSoup(html, "html.parser")

    for script_tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script_tag.string)
        except (json.JSONDecodeError, TypeError):
            continue

        if data.get("@type") != "Product":
            continue

        try:
            price_raw = data["offers"]["lowPrice"]
        except KeyError as e:
            raise KeyError(
                f"No se encontró offers.lowPrice en el JSON-LD de Jumbo: {e}\n"
                "Inspeccioná document.querySelectorAll('script[type=\"application/ld+json\"]') en la consola."
            )

        return Decimal(str(price_raw))

    raise ValueError(
        "No se encontró JSON-LD con @type 'Product' en la página de Jumbo"
    )
