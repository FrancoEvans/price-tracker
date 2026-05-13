import pytest
from httpx import AsyncClient


async def test_record_price_ok(client: AsyncClient, sample_product: dict):
    resp = await client.post(
        f"/products/{sample_product['id']}/prices",
        json={"price": "1500.50"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["price"] == "1500.50"
    assert data["currency"] == "ARS"
    assert data["product_id"] == sample_product["id"]
    assert "id" in data
    assert "recorded_at" in data


async def test_record_price_default_currency(client: AsyncClient, sample_product: dict):
    resp = await client.post(
        f"/products/{sample_product['id']}/prices",
        json={"price": "200.00"},
    )
    assert resp.json()["currency"] == "ARS"


async def test_record_price_custom_currency(client: AsyncClient, sample_product: dict):
    resp = await client.post(
        f"/products/{sample_product['id']}/prices",
        json={"price": "10.00", "currency": "USD"},
    )
    assert resp.status_code == 201
    assert resp.json()["currency"] == "USD"


async def test_record_price_product_not_found(client: AsyncClient):
    resp = await client.post(
        "/products/999999/prices",
        json={"price": "100.00"},
    )
    assert resp.status_code == 404


async def test_get_price_history_empty(client: AsyncClient, sample_product: dict):
    resp = await client.get(f"/products/{sample_product['id']}/prices")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_price_history_product_not_found(client: AsyncClient):
    resp = await client.get("/products/999999/prices")
    assert resp.status_code == 404


async def test_get_price_history_multiple_records(client: AsyncClient, sample_product: dict):
    product_id = sample_product["id"]
    await client.post(f"/products/{product_id}/prices", json={"price": "100.00"})
    await client.post(f"/products/{product_id}/prices", json={"price": "200.00"})
    await client.post(f"/products/{product_id}/prices", json={"price": "150.00"})

    resp = await client.get(f"/products/{product_id}/prices")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


async def test_get_price_history_ordered_desc(client: AsyncClient, sample_product: dict):
    """El historial debe estar ordenado de más reciente a más antiguo."""
    product_id = sample_product["id"]
    for price in ["100.00", "200.00", "300.00"]:
        await client.post(f"/products/{product_id}/prices", json={"price": price})

    history = (await client.get(f"/products/{product_id}/prices")).json()
    timestamps = [r["recorded_at"] for r in history]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_last_price_updates_after_record(client: AsyncClient, sample_product: dict):
    """last_price en GET /products/{id} refleja el precio más reciente."""
    product_id = sample_product["id"]

    await client.post(f"/products/{product_id}/prices", json={"price": "500.00"})
    product = (await client.get(f"/products/{product_id}")).json()
    assert product["last_price"] == "500.00"

    await client.post(f"/products/{product_id}/prices", json={"price": "450.00"})
    product = (await client.get(f"/products/{product_id}")).json()
    assert product["last_price"] == "450.00"
