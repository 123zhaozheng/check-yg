"""SQLAlchemy column type helpers shared across models.

`jsonb_column` gives us PostgreSQL ``JSONB`` in production and plain ``JSON``
under SQLite (tests), via SQLAlchemy's ``with_variant``. This keeps a single
model definition working on both dialects without if/else at call sites.
"""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB


def jsonb() -> type:
    """Return a column type that is JSONB on PostgreSQL, JSON on SQLite."""
    return JSONB().with_variant(JSON(), "sqlite")
