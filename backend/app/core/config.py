import os


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    def __init__(self) -> None:
        self.app_title = os.getenv("APP_TITLE", "Document Intelligence API")
        self.app_version = os.getenv("APP_VERSION", "0.1.0")
        self.api_v1_prefix = os.getenv("API_V1_PREFIX", "/api/v1").rstrip("/")
        default_origins = "http://127.0.0.1:5173,http://localhost:5173"
        self.allowed_origins = _split_csv(
            os.getenv("ALLOWED_ORIGINS", default_origins),
        )


settings = Settings()
