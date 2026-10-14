import os

from dotenv import load_dotenv

load_dotenv(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
)


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql://"):
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw_url


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

        self.database_url = _normalize_database_url(
            values.get(
                "DATABASE_URL",
                "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/document_intelligence",
            )
        )
        self.supabase_url = values.get("SUPABASE_URL", "")
        self.supabase_anon_key = values.get("SUPABASE_ANON_KEY", "")
        self.supabase_service_role_key = values.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.supabase_jwt_secret = values.get("SUPABASE_JWT_SECRET", "")
        self.openrouter_api_key = values.get("OPENROUTER_API_KEY", "")
        self.embedding_provider = values.get("EMBEDDING_PROVIDER", "openrouter")
        self.embedding_model = values.get(
            "EMBEDDING_MODEL", "openai/text-embedding-3-small"
        )
        self.embedding_dimensions = int(values.get("EMBEDDING_DIMENSIONS", "1536"))
        self.embedding_batch_size = int(values.get("EMBEDDING_BATCH_SIZE", "32"))
        self.embedding_timeout_seconds = float(
            values.get("EMBEDDING_TIMEOUT_SECONDS", "30")
        )
        self.embedding_max_retries = int(values.get("EMBEDDING_MAX_RETRIES", "2"))
        self.chunk_target_tokens = int(values.get("CHUNK_TARGET_TOKENS", "500"))
        self.chunk_overlap_tokens = int(values.get("CHUNK_OVERLAP_TOKENS", "75"))
        self.chunk_max_tokens = int(values.get("CHUNK_MAX_TOKENS", "700"))
        self.chunk_tokenizer_encoding = values.get(
            "CHUNK_TOKENIZER_ENCODING", "cl100k_base"
        )


settings = Settings()
