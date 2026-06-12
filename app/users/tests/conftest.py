import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.users.models.user import User

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:jk1019@localhost:5432/price_tracker_test",
)


@pytest.fixture(scope="session")
async def engine_test():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def test_session_factory(engine_test):
    return async_sessionmaker(engine_test, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
async def create_tables(engine_test):
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DELETE FROM alerts"))
        await conn.execute(text("DELETE FROM user_products"))
        await conn.execute(text("DELETE FROM price_records"))
        await conn.execute(text("DELETE FROM products"))
        await conn.execute(text("DELETE FROM users"))
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def clean_tables(engine_test):
    yield
    async with engine_test.begin() as conn:
        await conn.execute(text("DELETE FROM alerts"))
        await conn.execute(text("DELETE FROM user_products"))
        await conn.execute(text("DELETE FROM price_records"))
        await conn.execute(text("DELETE FROM products"))
        await conn.execute(text("DELETE FROM users"))


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


@pytest.fixture
async def user_with_telegram(test_session_factory):
    async with test_session_factory() as session:
        user = User(
            username="tguser",
            email="tg@example.com",
            telegram_id=123456789,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return {"id": user.id, "telegram_id": user.telegram_id}
