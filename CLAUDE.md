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

- `.env` — used by the app at runtime (`DATABASE_URL`, `TELEGRAM_BOT_TOKEN`) and by the bot (`API_BASE_URL`, plus `TELEGRAM_BOT_TOKEN` shared with the app). Both `Settings` (app) and `BotSettings` (bot) must set `extra: "ignore"` in `model_config` — they share this one file but each only declares its own subset of fields, so any field that belongs to the other one is "extra" from its point of view. This has broken twice already (once per class) when a new var was added for one side without the other tolerating it; if you add a new env var, don't assume this is handled automatically.
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
    models/            → User, UserProduct, Alert ORM models
    schemas/           → Pydantic schemas for users, user_products, alerts
    routers/           → HTTP handlers for /users and /users/{id}/products/{id}/alerts

scraper/
  main.py              → Entry point; runs a loop every 30 minutes per user_id
  fetcher.py           → Downloads raw HTML via httpx
  parsers/products/
    fravega.py         → Extracts price from __NEXT_DATA__ (Apollo/Next.js)
    jumbo.py           → Extracts price from JSON-LD (schema.org)

bot/                   → Telegram bot: /start (auto-registra), /track <url>, /list, /prices <n>, /alerta <n> <condicion> <valor>, /help, /ping

alembic/               → DB migration scripts
```

## Database tables

| Table | Columns |
|---|---|
| `products` | id, name, url (unique), category, created_at |
| `price_records` | id, product_id FK, price, currency (default ARS), recorded_at |
| `users` | id, username (unique), email (unique), telegram_id (BIGINT, nullable), created_at |
| `user_products` | id, user_id FK, product_id FK, added_at |
| `alerts` | id, user_product_id FK, condition (`percent_drop`\|`price_below`), threshold, triggered_at (nullable), created_at |

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

**`GET /products/?url=`** is an optional query param on the same list endpoint (not a separate route) — returns an empty list when there's no match, since "doesn't exist yet" is an expected case for the bot's `/track`, not an error.

**`get_user_products` (in `app/users/routers/users.py`) reuses `_last_price()` from `app/products/routers/products.py`** — it must compute `last_price` the same way the products router does; this was a bug once (always returned `null`) and now has a regression test.

**`GET /users/{id}/products` is ordered by `user_products.id`** (not arbitrary) — the bot relies on this to number products 1, 2, 3... consistently across calls.

**The numbers the bot shows (`/list`, `/prices <n>`, `/alerta <n>`) are per-user positions, not real `product_id`s** — resolved in `bot/main.py::resolve_product_id` by mapping position → `GET /users/{id}/products` index. Any new bot command that references "the user's Nth product" must go through this same helper, not accept a raw `product_id` from the user.

**Alerts are evaluated inside `POST /products/{id}/prices`** (`app/products/routers/prices.py`), not via a separate endpoint — the scraper's contract stays unchanged (it still just posts a price). Evaluation wraps in `try/except` so a Telegram send failure never fails the price write, which already committed. Logic lives in `app/users/routers/alerts.py::evaluate_alerts` (no separate `services/` layer — kept next to the router of the same resource).

**`percent_drop` compares against the immediately previous price**, not the historical minimum or the first price ever recorded — simplest option, and the most intuitive for "tell me if it just dropped."

**Alerts disarm after firing** — `triggered_at` is set once and never re-evaluated. A known race exists if two scraper instances (different `user_id`) post a price for the same shared product almost simultaneously: both could read `triggered_at IS NULL` before either commits, causing a duplicate Telegram message. Low-impact (duplicate notification, not data corruption); not addressed with locking yet.

**The API sends Telegram messages directly** via `app/core/telegram.py::send_telegram_message` (a plain httpx POST to `api.telegram.org`, not `python-telegram-bot`) — keeps the scraper's contract simple (still just posts prices) and centralizes the alert-firing logic in one place.

**Redundant `ix_<table>_id` indexes were dropped** from all five tables — they duplicated the index Postgres already creates for each primary key. Migrations `eaf1a705802d` (drop indexes) and `45a343679b6f` (add `alerts.triggered_at`) were kept separate so each is independently revertible.

**Product name from the scraper**: `scraper/main.py` has a `NAME_PARSERS` dict parallel to `PARSERS`; each site parser also exposes `parse_name(html) -> str | None` (never raises). The scraper PATCHes the real name only when the current name still equals the `/track` placeholder (`url[:60]`) — Frávega's exact name key in `__NEXT_DATA__` is unconfirmed (tries `name`/`title`/`productName`, falls back to `None`); Jumbo's JSON-LD `name` field is standard and reliable.


## Traceability
At the start of a session: read DEVLOG.md before doing anything.
At the end of a session where code was modified:
- overwrite "Current state" and "Next steps" with the new reality
- add a dated entry under "Log"
- if a technical decision with a trade-off was made, record it under "Decisions"
Do not touch "Objective" unless I define it explicitly.

## Keeping skills current

As the project grows (new stores, new bot commands, new resource types — flights, financial assets, etc.), the skills in `.claude/skills/` (`add-resource`, `add-bot-command`, `alembic-update`) must be updated to reflect new patterns as they emerge, not just left describing the state they were written in. When a session introduces a genuinely new pattern (e.g. a second kind of scraper parser, a non-store domain, a new bot interaction style like inline buttons), update the relevant skill file in the same session, not as a separate afterthought.