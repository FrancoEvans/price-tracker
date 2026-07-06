import asyncio
import logging
from decimal import Decimal
from urllib.parse import urlparse

import httpx

from scraper.fetcher import fetch_html
from scraper.parsers.products import fravega, jumbo

# Configuración básica del logger
# formato: timestamp + nivel (INFO/ERROR) + mensaje
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# por ahora corre localmente
API_BASE = "http://localhost:8000"

# tiempo entre ciclos de scraping (MINUTOS)
INTERVAL_MINUTES = 30

# asociar dominio con la funcion a usar (el scraper de esa URL)
PARSERS = {
    "www.fravega.com": fravega.parse_price,
    "fravega.com": fravega.parse_price,
    "www.jumbo.com.ar": jumbo.parse_price,
    "jumbo.com.ar": jumbo.parse_price,
}

# igual que PARSERS pero para extraer el nombre real del producto (dict hermano,
# no reemplaza a PARSERS para no arriesgar lo que ya funciona en produccion)
NAME_PARSERS = {
    "www.fravega.com": fravega.parse_name,
    "fravega.com": fravega.parse_name,
    "www.jumbo.com.ar": jumbo.parse_name,
    "jumbo.com.ar": jumbo.parse_name,
}

# GET a la API para obtener los productos asociados a user_id
async def get_products(client: httpx.AsyncClient, user_id: int) -> list[dict]:
    response = await client.get(f"{API_BASE}/users/{user_id}/products")
    response.raise_for_status()
    products = response.json()

    # deduplica: si el mismo URL aparece más de una vez en la respuesta, solo conserva la primera ocurrencia
    seen_urls: set[str] = set()
    unique = []
    for product in products:
        if product["url"] not in seen_urls:
            seen_urls.add(product["url"])
            unique.append(product)
    return unique

# registra el precio
async def post_price(
    client: httpx.AsyncClient,
    product_id: int,
    price: Decimal,
    currency: str = "ARS",
) -> dict:
    
    response = await client.post(
        f"{API_BASE}/products/{product_id}/prices",
        json={"price": str(price), "currency": currency},
    )
    # str(price) porque json.dumps() no sabe serializar decimal. Pydantic del otro lado lo convierte a decimal
    response.raise_for_status()
    return response.json()

# actualiza el nombre real del producto (usado cuando todavia tiene el placeholder de /track)
async def patch_product_name(client: httpx.AsyncClient, product_id: int, name: str) -> None:
    response = await client.patch(f"{API_BASE}/products/{product_id}", json={"name": name})
    response.raise_for_status()

# scrapea el prodcuto y lo guarda en la API
async def scrape_product(api_client: httpx.AsyncClient, product: dict) -> None:

    url = product["url"]
    product_id = product["id"]
    name = product["name"]

    # urlparse descompone una URL en sus partes
    # "https://www.fravega.com/p/notebook-xyz/" -> netloc = "www.fravega.com"
    domain = urlparse(url).netloc

    # determina que PARSER usar
    parser = PARSERS.get(domain)

    if parser is None:
        logger.warning(
            "Sin parser para dominio '%s' (producto id=%d '%s'). Saltando.",
            domain,
            product_id,
            name,
        )
        return

    try:
        logger.info("Scrapeando: %s", name)
        html = await fetch_html(url) # descarga el HTML del prodcuto
        price = parser(html) # extrae el precio
        await post_price(api_client, product_id, price) # lo guarda en la API
        logger.info("OK id=%d '%s' -> %.2f ARS", product_id, name, price)

        # si el nombre sigue siendo el placeholder que puso /track (url truncada), corregirlo
        if name == url[:60]:
            name_parser = NAME_PARSERS.get(domain)
            if name_parser is not None:
                real_name = name_parser(html)
                if real_name:
                    await patch_product_name(api_client, product_id, real_name)
                    logger.info("Nombre actualizado id=%d -> '%s'", product_id, real_name)

    except Exception as e:
        # si un producto falla, sigue con los demas
        # FUTURO: CONTADOR DE FALLOS CONSECUTIVOS PARA DESACTIVAR LOS PRODUCTOS QUE FALLAN MUCHO
        logger.error("ERROR id=%d '%s': %s", product_id, name, e)



async def main() -> None:

    import sys
    if len(sys.argv) < 2:
        print("Uso: python -m scraper.main <user_id>")
        sys.exit(1)
    user_id = int(sys.argv[1])

    logger.info("Scraper iniciado para user_id=%d. Intervalo: %d minutos.", user_id, INTERVAL_MINUTES)

    # Un solo cliente httpx para hablar con nuestra API durante toda la vida del proceso.
    async with httpx.AsyncClient() as api_client:
        while True:
            logger.info("** INICIO DEL CICLO **")

            try:
                products = await get_products(api_client, user_id)
                logger.info("%d productos a scrapear.", len(products))

                if products:
                    # asyncio.gather(): Scrapear todos los productos en paralelo
                    await asyncio.gather(
                        *[scrape_product(api_client, p) for p in products],
                        return_exceptions=True, # si una coroutine lanza una excepción, gather no cancela las demás
                    )
            except Exception as e:
                logger.error("No se pudo obtener la lista de productos: %s", e)

            logger.info("** FIN DEL CICLO ** -> Proximo ciclo en %d minutos)", INTERVAL_MINUTES)
            await asyncio.sleep(INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    # asyncio.run() es el punto de entrada para código async
    asyncio.run(main())
