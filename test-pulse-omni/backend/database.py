"""SQLite / SQLAlchemy session setup."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base
from .services.common import DATA_DIR, ensure_data_dirs

ensure_data_dirs()

DEFAULT_DB_PATH = DATA_DIR / "testpulse.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.as_posix()}")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """Create tables and make sure SQLite's parent directory exists."""
    if DATABASE_URL.startswith("sqlite:///"):
        db_file = Path(DATABASE_URL.removeprefix("sqlite:///"))
        if not db_file.is_absolute():
            db_file = (Path.cwd() / db_file).resolve()
        db_file.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
