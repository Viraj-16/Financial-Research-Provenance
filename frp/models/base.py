"""Declarative base and shared column helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all FRP ORM models."""


def utcnow() -> datetime:
    """Timezone-aware UTC timestamp used for all created/frozen times."""
    return datetime.now(timezone.utc)