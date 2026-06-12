# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

REST API + scraper + Telegram bot for tracking product prices over time. Users register products from sites like Frávega and Jumbo, the scraper runs automatically and saves price history, and the Telegram bot is the main user interface.

## Commands

```bash
# Run the dev server (auto-reloads on file changes)
uvicorn app.main:app --reload

# Run the scraper for a specific user
python -m scraper.main <user_id>

# Run all tests (requires price_tracker_test DB to exist)
pytest

# Run a single test file
pytest app/products/tests/test_products.py

# Run a single test by name
pytest app/products/tests/test_products.py -k "test_create_product"

# Run migrations
alembic upgrade head

# Generate a new migration after model changes
alembic revision --autogenerate -m "description"
```

## Environment

- `.env` — used by the app at runtime (`DATABASE_URL`)
- `.env.test` — sets `TEST_DATABASE_URL` for the test suite; loaded manually in `conftest.py` via `os.environ.get`
- Both databases must exist in PostgreSQL before running

## Architecture

```
app/
  main.py              → Creates FastAPI app, registers routers, handles lifespan (engine.dispose on shutdown)
  core/
    config.py          → Reads .env via pydantic-settings; single `settings` instance imported everywhere
    database.py        → Async engine + session factory; `get_db` FastAPI dependency yields one session per request
  products/
    models/            → Product, PriceRecord ORM models
    schemas/           → Pydantic schemas for products and prices
    routers/           → HTTP handlers for /products and /products/{id}/prices
    tests/             → Integration tests for products and prices
  users/
    models/            → User, UserProduct ORM models
    schemas/           → Pydantic schemas for users and user_products
    routers/           → HTTP handlers for /users

scraper/
  main.py              → Entry point; runs a loop every 30 minutes per user_id
  fetcher.py           → Downloads raw HTML via httpx
  parsers/products/
    fravega.py         → Extracts price from __NEXT_DATA__ (Apollo/Next.js)
    jumbo.py           → Extracts price from JSON-LD (schema.org)

bot/                   → Telegram bot (in progress)

alembic/               → DB migration scripts
```

## Database tables

| Table | Columns |
|---|---|
| `products` | id, name, url (unique), category, created_at |
| `price_records` | id, product_id FK, price, currency (default ARS), recorded_at |
| `users` | id, username (unique), email (unique), telegram_id (BIGINT, nullable), created_at |
| `user_products` | id, user_id FK, product_id FK, added_at |

## Key design decisions

**`users` ↔ `products` is many-to-many via `user_products`** — a product exists only once in the DB even if multiple users follow it.

**`telegram_id` is BIGINT** because Telegram user IDs exceed the INTEGER range.

**The scraper is an independent process** — `python -m scraper.main <user_id>` fetches the user's products from the API and scrapes them in parallel using `asyncio.gather`. It talks to the app via HTTP, not directly to the DB.

**The scraper deduplicates URLs** before scraping — if two users follow the same product, it is only fetched once per cycle.

**Parsers live in `scraper/parsers/products/`**, one per site. Adding a new site means adding a parser file and registering its domain in the `PARSERS` dict in `scraper/main.py`.

**The Telegram bot is a third independent process** that communicates with the API via HTTP.

**`last_price` is computed in the router**, not on the model — it requires a separate query and is treated as a derived API field, not a DB column.

**Circular import in models** — `Product` ↔ `PriceRecord` use `from __future__ import annotations` to make type hints lazy, then import each other at the bottom of their files after the class definition.

**Tests use a real PostgreSQL database** (`price_tracker_test`), not mocks or SQLite. The fixture strategy:
- `engine_test` + `create_tables`: session-scoped — create all tables once, drop at end
- `clean_tables`: function-scoped autouse — deletes rows after each test (respects FK order: `price_records` before `products`)
- `client`: function-scoped — overrides `get_db` dependency with the test session factory

**Alembic uses psycopg2 (sync)** for migrations even though the app uses asyncpg (async) at runtime. `alembic/env.py` must import all model modules explicitly.

**`PATCH` uses `model_dump(exclude_unset=True)`** so only the fields the client sent are updated.

**`url` is unique** on `products` — duplicate detection returns 409, not a DB-level 500.


## Traceability
At the start of a session: read DEVLOG.md before doing anything.
At the end of a session where code was modified:
- overwrite "Current state" and "Next steps" with the new reality
- add a dated entry under "Log"
- if a technical decision with a trade-off was made, record it under "Decisions"
Do not touch "Objective" unless I define it explicitly.