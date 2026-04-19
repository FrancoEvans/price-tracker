from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# --- Importar Base y todos los modelos ---
#
# Si los modelos no se importan aquí, Base.metadata queda vacío y
# --autogenerate genera una migración vacía (o peor, borra las tablas).
# app/models/__init__.py está vacío, así que importamos cada módulo directamente.
from app.database import Base
import app.models.product  # noqa: F401 — registra Product en Base.metadata
import app.models.price    # noqa: F401 — registra PriceRecord en Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target_metadata le dice a Alembic cuál es el estado "deseado" del schema.
# Compara esto contra la DB real para generar las migraciones.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Modo offline: genera el SQL sin conectarse a la DB.

    Útil para revisar el SQL que se va a ejecutar antes de aplicarlo,
    o para generar scripts de migración para aplicar manualmente.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo online: se conecta a la DB con psycopg2 y aplica las migraciones.

    Alembic es una herramienta de CLI — no necesita async. Usa psycopg2
    (driver síncrono) que es independiente del asyncpg que usa la app en runtime.
    NullPool evita reutilizar conexiones, correcto para una operación puntual.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
