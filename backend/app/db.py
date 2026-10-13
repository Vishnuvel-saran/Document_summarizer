import os
from contextlib import contextmanager
from urllib.parse import quote, urlsplit, urlunsplit

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()


def _normalize_database_url(raw_url: str) -> str:
    if not raw_url:
        return raw_url

    if raw_url.startswith("postgresql://"):
        parsed = urlsplit(raw_url)
        if parsed.username and parsed.password:
            encoded_password = quote(parsed.password, safe="")
            hostname = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            netloc = f"{parsed.username}:{encoded_password}@{hostname}{port}"
            return urlunsplit(
                (
                    "postgresql+psycopg",
                    netloc,
                    parsed.path,
                    parsed.query,
                    parsed.fragment,
                )
            )

    return raw_url


class DBSettings:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        values = env or os.environ
        self.database_url = _normalize_database_url(
            values.get(
                "DATABASE_URL",
                "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/document_intelligence",
            )
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
