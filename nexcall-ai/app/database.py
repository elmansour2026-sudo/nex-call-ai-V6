"""
NexCall AI — Couche base de données
SQLAlchemy async avec support SQLite et PostgreSQL
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Classe de base pour tous les modèles SQLAlchemy"""
    pass


# Création du moteur async
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

# Factory de sessions
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    """Dépendance FastAPI pour obtenir une session de base de données"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialise la base de données et crée toutes les tables"""
    # Import des modèles pour déclencher leur enregistrement
    from app.models import (  # noqa: F401
        agent, call, lead, campaign, prospect,
        qualification, configuration, blacklist, call_script,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Auto-migration légère : ajoute les colonnes manquantes sur les tables
        # déjà existantes (utile en production PostgreSQL où create_all ne gère
        # pas l'ajout de colonnes à une table déjà créée).
        await conn.run_sync(_add_missing_columns)

    logger.info("✅ Base de données initialisée avec succès")


def _add_missing_columns(sync_conn) -> None:
    """Compare le schéma des modèles aux tables réelles et ajoute les colonnes
    manquantes via ALTER TABLE. Sûr et idempotent ; ne supprime jamais rien."""
    from sqlalchemy import inspect as sa_inspect
    dialect = sync_conn.dialect.name
    inspector = sa_inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_cols:
                continue
            try:
                col_type = column.type.compile(dialect=sync_conn.dialect)
            except Exception:
                col_type = "VARCHAR"
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'
            # Valeur par défaut éventuelle pour ne pas casser les lignes existantes
            default = getattr(column, "default", None)
            if default is not None and getattr(default, "arg", None) is not None and not callable(default.arg):
                val = default.arg
                if isinstance(val, bool):
                    val = ("TRUE" if val else "FALSE") if dialect != "sqlite" else ("1" if val else "0")
                elif isinstance(val, str):
                    val = "'" + val.replace("'", "''") + "'"
                ddl += f" DEFAULT {val}"
            try:
                from sqlalchemy import text as _sql_text
                sync_conn.execute(_sql_text(ddl))
                logger.info(f"[migration] Colonne ajoutee : {table.name}.{column.name}")
            except Exception as e:
                logger.warning(f"[migration] Impossible d'ajouter {table.name}.{column.name}: {e}")


async def drop_all_tables() -> None:
    """Supprime toutes les tables (utiliser avec précaution)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
