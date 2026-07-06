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


async def test_create_user_with_telegram_id_ok(client: AsyncClient):
    resp = await client.post(
        "/users/",
        json={"username": "nuevo", "email": "nuevo@example.com", "telegram_id": 42},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["telegram_id"] == 42


async def test_create_user_duplicate_telegram_id(client: AsyncClient, user_with_telegram: dict):
    resp = await client.post(
        "/users/",
        json={
            "username": "otro_username",
            "email": "otro@example.com",
            "telegram_id": user_with_telegram["telegram_id"],
        },
    )
    assert resp.status_code == 409


async def test_get_user_products_empty(client: AsyncClient, user_with_telegram: dict):
    resp = await client.get(f"/users/{user_with_telegram['id']}/products")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_user_products_includes_last_price(client: AsyncClient, user_with_telegram: dict):
    """Regresión: get_user_products debía calcular last_price igual que products.list_products."""
    product = (
        await client.post(
            "/products/",
            json={"name": "Con Precio Users", "url": "https://example.com/con-precio-users"},
        )
    ).json()
    await client.post(f"/products/{product['id']}/prices", json={"price": "1234.50"})
    await client.post(
        f"/users/{user_with_telegram['id']}/products",
        json={"product_id": product["id"]},
    )

    resp = await client.get(f"/users/{user_with_telegram['id']}/products")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["last_price"] == "1234.50"


async def test_get_user_products_stable_order(client: AsyncClient, user_with_telegram: dict):
    """El orden debe ser estable (por user_products.id) para que el bot pueda numerar posiciones."""
    user_id = user_with_telegram["id"]
    urls = [
        "https://example.com/orden-1",
        "https://example.com/orden-2",
        "https://example.com/orden-3",
    ]
    created_ids = []
    for i, url in enumerate(urls):
        product = (
            await client.post("/products/", json={"name": f"Orden {i}", "url": url})
        ).json()
        created_ids.append(product["id"])
        await client.post(f"/users/{user_id}/products", json={"product_id": product["id"]})

    first = (await client.get(f"/users/{user_id}/products")).json()
    second = (await client.get(f"/users/{user_id}/products")).json()

    assert [p["id"] for p in first] == created_ids
    assert [p["id"] for p in second] == created_ids
