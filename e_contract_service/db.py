from __future__ import annotations

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


_default_sqlite = f"sqlite+pysqlite:///{(Path(__file__).resolve().parent / 'e_contract_local.db').as_posix()}"
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip() or _default_sqlite
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()