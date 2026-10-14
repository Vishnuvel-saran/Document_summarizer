from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import db as db_module
from app.core.config import Settings
from app.main import app

client = TestClient(app)


def test_database_settings_validates_configuration() -> None:
    settings = Settings(
        {
            "DATABASE_URL": "postgresql+psycopg://user:pass@localhost:5432/app",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_ANON_KEY": "anon-key",
        }
    )

    assert settings.database_url == "postgresql+psycopg://user:pass@localhost:5432/app"
    assert settings.supabase_url == "https://example.supabase.co"
    assert settings.supabase_anon_key == "anon-key"


def test_db_health_returns_ok_when_database_is_available(monkeypatch) -> None:
    monkeypatch.setattr("app.db.is_database_available", lambda: True)

    response = client.get("/api/v1/db-health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_db_health_returns_503_when_database_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr("app.db.is_database_available", lambda: False)

    response = client.get("/api/v1/db-health")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_db_session_commits_successful_changes(monkeypatch) -> None:
    test_engine = create_engine("sqlite://")
    monkeypatch.setattr(db_module, "engine", test_engine)

    with db_module.db_session() as connection:
        connection.execute(text("CREATE TABLE documents (id TEXT PRIMARY KEY)"))
        connection.execute(text("INSERT INTO documents (id) VALUES ('doc-123')"))

    with test_engine.connect() as connection:
        saved_id = connection.scalar(text("SELECT id FROM documents"))

    assert saved_id == "doc-123"
    test_engine.dispose()
