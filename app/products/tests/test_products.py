import pytest
from httpx import AsyncClient


async def test_create_product_ok(client: AsyncClient):
    resp = await client.post(
        "/products/",
        json={"name": "Notebook X", "url": "https://example.com/notebook-x", "category": "tech"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Notebook X"
    assert data["url"] == "https://example.com/notebook-x"
    assert data["category"] == "tech"
    assert data["last_price"] is None
    assert "id" in data
    assert "created_at" in data


async def test_create_product_no_category(client: AsyncClient):
    resp = await client.post(
        "/products/",
        json={"name": "Sin Categoria", "url": "https://example.com/sin-cat"},
    )
    assert resp.status_code == 201
    assert resp.json()["category"] is None


async def test_create_product_duplicate_url(client: AsyncClient):
    payload = {"name": "Producto A", "url": "https://example.com/duplicado"}
    await client.post("/products/", json=payload)
    resp = await client.post("/products/", json=payload)
    assert resp.status_code == 409


async def test_create_product_missing_fields(client: AsyncClient):
    resp = await client.post("/products/", json={"name": "Sin URL"})
    assert resp.status_code == 422


async def test_list_products_empty(client: AsyncClient):
    resp = await client.get("/products/")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_products_with_data(client: AsyncClient):
    await client.post(
        "/products/",
        json={"name": "Prod 1", "url": "https://example.com/prod-1"},
    )
    await client.post(
        "/products/",
        json={"name": "Prod 2", "url": "https://example.com/prod-2"},
    )
    resp = await client.get("/products/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_list_products_includes_last_price(client: AsyncClient):
    created = (
        await client.post(
            "/products/",
            json={"name": "Con Precio", "url": "https://example.com/con-precio"},
        )
    ).json()
    await client.post(
        f"/products/{created['id']}/prices",
        json={"price": "999.99"},
    )

    products = (await client.get("/products/")).json()
    product = next(p for p in products if p["id"] == created["id"])
    assert product["last_price"] == "999.99"


async def test_list_products_filter_by_url_match(client: AsyncClient):
    created = (
        await client.post(
            "/products/",
            json={"name": "Filtrado", "url": "https://example.com/filtrado"},
        )
    ).json()
    resp = await client.get("/products/", params={"url": "https://example.com/filtrado"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == created["id"]


async def test_list_products_filter_by_url_no_match(client: AsyncClient):
    resp = await client.get("/products/", params={"url": "https://example.com/no-existe"})
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_product_ok(client: AsyncClient):
    created = (
        await client.post(
            "/products/",
            json={"name": "Get Me", "url": "https://example.com/get-me"},
        )
    ).json()
    resp = await client.get(f"/products/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


async def test_get_product_not_found(client: AsyncClient):
    resp = await client.get("/products/999999")
    assert resp.status_code == 404


async def test_update_product_ok(client: AsyncClient):
    created = (
        await client.post(
            "/products/",
            json={"name": "Original", "url": "https://example.com/update-me"},
        )
    ).json()
    resp = await client.patch(
        f"/products/{created['id']}",
        json={"name": "Actualizado"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Actualizado"


async def test_update_product_partial(client: AsyncClient):
    """PATCH solo modifica los campos enviados; los demás quedan intactos."""
    created = (
        await client.post(
            "/products/",
            json={"name": "Partial", "url": "https://example.com/partial", "category": "A"},
        )
    ).json()
    resp = await client.patch(
        f"/products/{created['id']}",
        json={"category": "B"},
    )
    data = resp.json()
    assert data["category"] == "B"
    assert data["name"] == "Partial"
    assert data["url"] == "https://example.com/partial"


async def test_update_product_not_found(client: AsyncClient):
    resp = await client.patch("/products/999999", json={"name": "X"})
    assert resp.status_code == 404


async def test_delete_product_ok(client: AsyncClient):
    created = (
        await client.post(
            "/products/",
            json={"name": "Borrar", "url": "https://example.com/borrar"},
        )
    ).json()
    resp = await client.delete(f"/products/{created['id']}")
    assert resp.status_code == 204
    assert resp.content == b""


async def test_delete_product_not_found(client: AsyncClient):
    resp = await client.delete("/products/999999")
    assert resp.status_code == 404


async def test_delete_product_cascades_prices(client: AsyncClient):
    """Borrar un producto elimina sus price_records en cascada."""
    created = (
        await client.post(
            "/products/",
            json={"name": "Con Precios", "url": "https://example.com/cascade"},
        )
    ).json()
    product_id = created["id"]
    await client.post(f"/products/{product_id}/prices", json={"price": "100.00"})

    await client.delete(f"/products/{product_id}")

    # El producto ya no existe → el endpoint de precios devuelve 404
    resp = await client.get(f"/products/{product_id}/prices")
    assert resp.status_code == 404
