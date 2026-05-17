# FETCHER: DESCARGA HTML DE UNA PAGINA

import httpx

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

async def fetch_html(url: str) -> str:
    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=10, # TimeoutException si no responde en 10 segundos
        follow_redirects=True, # porque algunos sitios redirigen (http -> https) o (www. -> www)
    ) as client:
        response = await client.get(url)

        response.raise_for_status() # excepción para status 4XX o 5XX

        return response.text
