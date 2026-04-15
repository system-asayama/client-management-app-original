from __future__ import annotations

from .db import Base, engine
from . import models  # noqa: F401


def run_migrations() -> None:
    Base.metadata.create_all(bind=engine)