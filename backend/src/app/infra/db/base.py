"""SQLAlchemy declarative base with deterministic constraint-naming convention.

Every ORM model in the backend inherits from :class:`Base` so that Alembic
autogenerate produces stable constraint names across runs (e.g. ``ix_``,
``uq_``, ``ck_``, ``fk_``, ``pk_``). Without a naming convention, autogenerate
emits fresh random suffixes that cause spurious migration diffs.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

__all__ = ["Base", "metadata", "NAMING_CONVENTION"]


NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all BCMS ORM models.

    All model classes under ``app.domain.*`` and ``app.core.security`` must
    inherit from this class so their tables register with the shared
    :data:`metadata` instance and pick up the naming convention.
    """

    metadata = metadata
