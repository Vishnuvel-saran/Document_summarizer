import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))


def _normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql://", 1)
    return raw_url


class DBSettings:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        values = env or os.environ
        self.database_url = values.get(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/document_intelligence",
        )
        self.supabase_url = values.get("SUPABASE_URL", "")
        self.supabase_anon_key = values.get("SUPABASE_ANON_KEY", "")


settings = DBSettings()
engine: Engine = create_engine(settings.database_url, pool_pre_ping=True)


@contextmanager
def db_session():
    with engine.connect() as connection:
        yield connection


def is_database_available() -> bool:
    try:
        with db_session() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except (SQLAlchemyError, OSError):
        return False
