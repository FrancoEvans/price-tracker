from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


@pytest.fixture
async def tracked_product(client: AsyncClient, user_with_telegram: dict):
    """Producto creado y asociado al usuario de user_with_telegram."""
    product = (
        await client.post(
            "/products/",
            json={"name": "Alert Product", "url": "https://example.com/alert-product"},
        )
    ).json()
    await client.post(
        f"/users/{user_with_telegram['id']}/products",
        json={"product_id": product["id"]},
    )
    return product


async def test_create_alert_ok(client: AsyncClient, user_with_telegram: dict, tracked_product: dict):
    resp = await client.post(
        f"/users/{user_with_telegram['id']}/products/{tracked_product['id']}/alerts",
        json={"condition": "price_below", "threshold": "9000"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["condition"] == "price_below"
    assert data["threshold"] == "9000.00"
    assert data["triggered_at"] is None


async def test_create_alert_invalid_condition(
    client: AsyncClient, user_with_telegram: dict, tracked_product: dict
):
    resp = await client.post(
        f"/users/{user_with_telegram['id']}/products/{tracked_product['id']}/alerts",
        json={"condition": "bogus_condition", "threshold": "9000"},
    )
    assert resp.status_code == 422


async def test_create_alert_user_not_tracking_product(client: AsyncClient, user_with_telegram: dict):
    other_product = (
        await client.post(
            "/products/",
            json={"name": "Not tracked", "url": "https://example.com/not-tracked"},
        )
    ).json()
    resp = await client.post(
        f"/users/{user_with_telegram['id']}/products/{other_product['id']}/alerts",
        json={"condition": "price_below", "threshold": "9000"},
    )
    assert resp.status_code == 404


async def test_list_alerts_empty(client: AsyncClient, user_with_telegram: dict, tracked_product: dict):
    resp = await client.get(
        f"/users/{user_with_telegram['id']}/products/{tracked_product['id']}/alerts"
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_alerts_with_data(
    client: AsyncClient, user_with_telegram: dict, tracked_product: dict
):
    await client.post(
        f"/users/{user_with_telegram['id']}/products/{tracked_product['id']}/alerts",
        json={"condition": "price_below", "threshold": "9000"},
    )
    resp = await client.get(
        f"/users/{user_with_telegram['id']}/products/{tracked_product['id']}/alerts"
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# --- evaluación end-to-end (disparada desde POST /products/{id}/prices) ---
#
# send_telegram_message se mockea porque estos tests no deben pegarle a la API
# real de Telegram; se mockea sobre el símbolo importado en app.users.routers.alerts,
# no en app.core.telegram, porque ya fue importado por nombre ahí.

@pytest.fixture
def mock_send_telegram(monkeypatch):
    mock = AsyncMock()
    monkeypatch.setattr("app.users.routers.alerts.send_telegram_message", mock)
    return mock


async def test_price_below_triggers_alert_and_marks_triggered_at(
    client: AsyncClient, user_with_telegram: dict, tracked_product: dict, mock_send_telegram
):
    user_id = user_with_telegram["id"]
    product_id = tracked_product["id"]

    await client.post(
        f"/users/{user_id}/products/{product_id}/alerts",
        json={"condition": "price_below", "threshold": "9000"},
    )

    resp = await client.post(f"/products/{product_id}/prices", json={"price": "8500"})
    assert resp.status_code == 201

    alerts = (await client.get(f"/users/{user_id}/products/{product_id}/alerts")).json()
    assert alerts[0]["triggered_at"] is not None
    mock_send_telegram.assert_awaited_once()


async def test_percent_drop_triggers_on_second_price_not_first(
    client: AsyncClient, user_with_telegram: dict, tracked_product: dict, mock_send_telegram
):
    user_id = user_with_telegram["id"]
    product_id = tracked_product["id"]

    await client.post(
        f"/users/{user_id}/products/{product_id}/alerts",
        json={"condition": "percent_drop", "threshold": "10"},
    )

    # primer precio: no hay "anterior", no puede disparar
    await client.post(f"/products/{product_id}/prices", json={"price": "10000"})
    alerts = (await client.get(f"/users/{user_id}/products/{product_id}/alerts")).json()
    assert alerts[0]["triggered_at"] is None
    mock_send_telegram.assert_not_awaited()

    # segundo precio: bajó 15% respecto al anterior (>= 10% threshold) -> dispara
    await client.post(f"/products/{product_id}/prices", json={"price": "8500"})
    alerts = (await client.get(f"/users/{user_id}/products/{product_id}/alerts")).json()
    assert alerts[0]["triggered_at"] is not None
    mock_send_telegram.assert_awaited_once()


async def test_alert_does_not_retrigger_once_triggered(
    client: AsyncClient, user_with_telegram: dict, tracked_product: dict, mock_send_telegram
):
    user_id = user_with_telegram["id"]
    product_id = tracked_product["id"]

    await client.post(
        f"/users/{user_id}/products/{product_id}/alerts",
        json={"condition": "price_below", "threshold": "9000"},
    )

    await client.post(f"/products/{product_id}/prices", json={"price": "8500"})
    mock_send_telegram.assert_awaited_once()

    # otro precio que también cumple la condición -> no debe re-disparar
    await client.post(f"/products/{product_id}/prices", json={"price": "8000"})
    mock_send_telegram.assert_awaited_once()
