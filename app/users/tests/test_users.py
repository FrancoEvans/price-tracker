from httpx import AsyncClient


async def test_get_user_by_telegram_ok(client: AsyncClient, user_with_telegram: dict):
    resp = await client.get(f"/users/by-telegram/{user_with_telegram['telegram_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == user_with_telegram["id"]
    assert data["telegram_id"] == user_with_telegram["telegram_id"]


async def test_get_user_by_telegram_not_found(client: AsyncClient):
    resp = await client.get("/users/by-telegram/999999999")
    assert resp.status_code == 404
