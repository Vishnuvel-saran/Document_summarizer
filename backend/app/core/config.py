import os


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        values = env if env is not None else os.environ
        self.app_title = values.get("APP_TITLE", "Document Intelligence API")
        self.app_version = values.get("APP_VERSION", "0.1.0")
        self.api_v1_prefix = values.get("API_V1_PREFIX", "/api/v1").rstrip("/")

        default_origins = "http://127.0.0.1:5173,http://localhost:5173"
        self.allowed_origins = _split_csv(
            values.get("ALLOWED_ORIGINS", default_origins),
        )

        self.database_url = values.get(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/document_intelligence",
        )
        self.supabase_url = values.get("SUPABASE_URL", "")
        self.supabase_anon_key = values.get("SUPABASE_ANON_KEY", "")
        self.supabase_service_role_key = values.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.supabase_jwt_secret = values.get("SUPABASE_JWT_SECRET", "")


settings = Settings()
