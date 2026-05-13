import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:jk1019@localhost:5432/price_tracker_test",
)


# --- engine: session scope — un solo engine para toda la corrida de tests ---

@pytest.fixture(scope="session")
async def engine_test():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


# --- session factory: session scope — reutilizada por todos los tests ---
#
# No es async porque `async_sessionmaker(...)` es sincrónico — solo configura
# cómo se van a crear las sesiones, no crea ninguna todavía.

@pytest.fixture(scope="session")
def test_session_factory(engine_test):
    return async_sessionmaker(engine_test, expire_on_commit=False)


# --- tablas: session scope + autouse — CREATE al inicio, DROP al final ---
#
# También limpia datos residuales de corridas anteriores al arrancar.
# Esto evita que un test fallen en la primera corrida después de una
# sesión de tests que fue interrumpida antes de que el cleanup terminara.

@pytest.fixture(scope="session", autouse=True)
async def create_tables(engine_test):
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DELETE FROM price_records"))
        await conn.execute(text("DELETE FROM products"))
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# --- limpieza: function scope + autouse — borra los datos después de cada test ---
#
# Cada test corre con tablas vacías. No usamos el truco de rollback porque
# asyncpg no soporta transacciones anidadas sin savepoints, y el approach
# de compartir una conexión entre fixture y handler genera conflictos.
# En cambio: los commits suceden normalmente, y después del test borramos todo.

@pytest.fixture(autouse=True)
async def clean_tables(engine_test):
    yield
    async with engine_test.begin() as conn:
        # Borrar en orden: primero la tabla hijo (FK), luego la padre
        await conn.execute(text("DELETE FROM price_records"))
        await conn.execute(text("DELETE FROM products"))


# --- cliente HTTP: function scope — cada test tiene su propio cliente ---
#
# override_get_db reemplaza la dependencia get_db de FastAPI.
# Cada request crea su propia sesión (igual que en producción),
# así no hay estado compartido entre requests del mismo test.

@pytest.fixture
async def client(test_session_factory):
    async def override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# --- producto de ejemplo: conveniencia para tests de precios ---

@pytest.fixture
async def sample_product(client):
    resp = await client.post(
        "/products/",
        json={
            "name": "Test Product",
            "url": "https://example.com/product-1",
            "category": "electronics",
        },
    )
    return resp.json()
