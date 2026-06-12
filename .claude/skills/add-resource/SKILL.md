---
name: add-resource
description: >
  Use when adding any new resource, entity, domain, or table to the API.
  Triggers on: "add a new resource", "new entity", "new table", "scaffold X",
  "I need endpoints for X", "add the Y domain", "create a model for X".
  Walks through all five layers (model → schema → router → migration → tests)
  in the order the project requires, enforcing decisions before code.
---

# Add a new resource

Work through each step in order. Settle the design decision at the top of each
step before writing any code for that layer — every layer depends on the
previous one being correct.

---

## 1. Name the resource and locate its domain

Decide:
- Resource name (snake_case for files/tables, singular PascalCase for the class,
  snake_case plural for `__tablename__`)
- Does a domain directory for this resource already exist under `app/`?
  - **Yes** (e.g. adding `PriceRecord` to an already-existing `products/`):
    skip directory creation; add files alongside the existing ones.
  - **No** (genuinely new domain): create the full tree:
    ```
    app/<domain>/
      __init__.py
      models/__init__.py
      schemas/__init__.py
      routers/__init__.py
      tests/__init__.py
    ```

---

## 2. Write the model (`app/<domain>/models/<model>.py`)

Decide before writing:
- Every column, its SQLAlchemy type, and nullability
- Which FK columns exist; each gets `ondelete="CASCADE"` and `index=True`
- Which columns need `unique=True`
- Whether any relationship side owns `cascade="all, delete-orphan"`
- Whether a cross-model relationship creates a circular import

Required conventions — match these exactly:

- First line: `from __future__ import annotations`
- `Base` imported from `app.core.database`
- Column order: `id` first, `created_at` last, everything else in between
- `id`: `Mapped[int] = mapped_column(primary_key=True, index=True)`
- `created_at`: `Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())`
- FK column pattern: `Mapped[int] = mapped_column(ForeignKey("table.id", ondelete="CASCADE"), nullable=False, index=True)`
- Nullable optional fields: `Mapped[str | None]` with `nullable=True`
- Circular imports: put cross-model imports at the **bottom** of the file, after
  the class definition, with `# noqa: E402 — resolves circular import`

---

## 3. Write the schemas (`app/<domain>/schemas/<schema>.py`)

Decide before writing:
- Which fields are required on Create vs. have a default
- Which fields are patchable (all become `| None = None` on Update)
- Any computed fields that appear only on Read (not stored in DB)

Schema hierarchy — this exact pattern every time:

```
<Resource>Base(BaseModel)          — shared required fields
<Resource>Create(<Resource>Base)   — creation-only fields; often just `pass`
<Resource>Update(BaseModel)        — all fields optional; does NOT inherit Base
<Resource>Read(<Resource>Base)     — adds id, created_at, any computed fields
```

- Only `<Resource>Read` gets `model_config = {"from_attributes": True}`
- `<Resource>Update` inherits `BaseModel` directly, never the Base schema

---

## 4. Write the router (`app/<domain>/routers/<router>.py`)

Decide before writing:
- Which HTTP verbs this resource needs
- The URL prefix and tag name
- Any unique constraints that require explicit 409 handling

Required conventions — match these exactly:

- `import logging` + `logger = logging.getLogger(__name__)` at the top
- `router = APIRouter(prefix="/<resources>", tags=["<resources>"])`
- DB dependency typed as `db: AsyncSession = Depends(get_db)`
- Query pattern: `result = await db.execute(select(Model)...)` → `result.scalar_one_or_none()`
- `POST` → `status_code=201`, sequence: `db.add()` → `await db.commit()` → `await db.refresh()`
- `PATCH` → `data.model_dump(exclude_unset=True)` + `setattr` loop → `await db.commit()` → `await db.refresh()`
- `DELETE` → `status_code=204`, sequence: `await db.delete(obj)` → `await db.commit()`
- `logger.info(...)` on create and delete only — not on reads or updates
- 404: `raise HTTPException(status_code=404, detail="<Resource> not found")`
- 409 for unique constraint violations: SELECT for the duplicate first; if found, raise before inserting

---

## 5. Register the router in `app/main.py`

**Gotcha:** forgetting this leaves the router silently unreachable — no startup
error, every endpoint returns 404.

Add the import and `include_router` call alongside the existing ones:

```python
from app.<domain>.routers import <router_module>
# ...
app.include_router(<router_module>.router)
```

---

## 6. Run the migration

Delegate to the **`alembic-update`** skill. It owns the full migration workflow,
including the check that the new model is imported in `alembic/env.py`.

---

## 7. Write the tests (`app/<domain>/tests/`)

If adding to an **existing domain**, the domain conftest.py already exists.
Extend `clean_tables` to delete rows from the new table in FK-safe order (before
the parent tables it depends on), and add the new `sample_<resource>` fixture if
needed. Do not create a second conftest.py.

If creating a **new domain**, create `conftest.py` following this fixture pattern:

| Fixture | Scope | autouse | Purpose |
|---|---|---|---|
| `engine_test` | session | — | `create_async_engine(TEST_DATABASE_URL)` |
| `test_session_factory` | session | — | `async_sessionmaker(engine_test, expire_on_commit=False)` |
| `create_tables` | session | ✓ | `Base.metadata.create_all`, clear stale rows at startup, drop at teardown |
| `clean_tables` | function | ✓ | yield → delete rows in FK order (children before parents) |
| `client` | function | — | override `get_db`, use `ASGITransport(app=app)` |
| `sample_<resource>` | function | — | POST one row; for use by other test files |

`clean_tables` must delete in FK-safe order: child tables first, then parent
tables. `create_tables` must also clear stale rows from prior interrupted runs
at startup (before `yield`).

Create `test_<resource>.py`. Required cases:

- `test_create_<resource>_ok` — 201, verify every returned field
- `test_create_<resource>_missing_fields` — 422
- `test_create_<resource>_duplicate_<unique_field>` — 409 *(skip if no unique constraint)*
- `test_list_<resources>_empty` — 200, empty list
- `test_list_<resources>_with_data` — 200, correct count
- `test_get_<resource>_ok` — 200, correct `id`
- `test_get_<resource>_not_found` — 404
- `test_update_<resource>_ok` — 200, changed field updated
- `test_update_<resource>_partial` — PATCH only changes sent fields; untouched fields unchanged
- `test_update_<resource>_not_found` — 404
- `test_delete_<resource>_ok` — 204, empty body
- `test_delete_<resource>_not_found` — 404
- `test_delete_<resource>_cascades_<children>` — *(only if the model has `cascade="all, delete-orphan"` children)*

Naming: `test_<verb>_<resource>_<outcome>`. All functions are plain `async def`,
no test classes.
