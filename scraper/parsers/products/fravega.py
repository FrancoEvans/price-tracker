import json
from decimal import Decimal

from bs4 import BeautifulSoup


def parse_price(html: str) -> Decimal: # Para precios => Decimal

    soup = BeautifulSoup(html, "html.parser")

    script_tag = soup.find("script", {"id": "__NEXT_DATA__"}) # estructura del HTML en fravega.txt

    if not script_tag:
        # el sitio cambió su estructura, o bloquearon IP o user-agent
        raise ValueError('No se encontro __NEXT_DATA__ en la pagina de fravega -> el sitio cambio o nos bloquearon')

    # script_tag.string es el contenido de texto del tag
    # json.loads() lo convierte en un dict de Python.
    data = json.loads(script_tag.string)

    try:
        # Fravega usa Apollo Client
        apollo = data["props"]["pageProps"]["__APOLLO_STATE__"]

        root = apollo["ROOT_QUERY"]

        # sku({"code":"XXXXX"})    
        sku_key = next(k for k in root if k.startswith("sku(")) # clave dinamica
        sku = root[sku_key]
        
        # pricing({"channel":"fravega-ecommerce"})
        pricing_key = next(k for k in sku if k.startswith("pricing(")) # clave dinamica
        pricing = sku[pricing_key]

        # pricing es una lista -> tomamos el primer elemento (canal ecommerce)
        # salePrice -> el precio de oferta, no el tachado (de lista)
        price_raw = pricing[0]["salePrice"] 

    except (KeyError, StopIteration) as e:
        raise KeyError(
            f"No se pudo extraer el precio de FRAVEGA: {e}\n"
        )

    return Decimal(str(price_raw))


def parse_name(html: str) -> str | None:
    """Extrae el nombre del producto. Nunca lanza: devuelve None si no puede.

    La clave exacta del nombre dentro de `sku` no está confirmada con HTML real
    (fravega.txt solo documenta la estructura del precio) — se prueban varias
    claves candidatas y se cae a None si ninguna existe.
    """
    soup = BeautifulSoup(html, "html.parser")

    script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script_tag:
        return None

    try:
        data = json.loads(script_tag.string)
        apollo = data["props"]["pageProps"]["__APOLLO_STATE__"]
        root = apollo["ROOT_QUERY"]
        sku_key = next(k for k in root if k.startswith("sku("))
        sku = root[sku_key]
        return sku.get("name") or sku.get("title") or sku.get("productName")
    except (KeyError, StopIteration, TypeError, json.JSONDecodeError):
        return None
