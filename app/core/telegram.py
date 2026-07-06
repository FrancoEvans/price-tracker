import httpx

from app.core.config import settings

TELEGRAM_API_BASE = "https://api.telegram.org"


async def send_telegram_message(chat_id: int, text: str) -> None:
    url = f"{TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": text})
        response.raise_for_status()
