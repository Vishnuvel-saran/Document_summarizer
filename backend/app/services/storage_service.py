from __future__ import annotations

from app.core.config import settings


class SupabaseStorageService:
    def __init__(self) -> None:
        self.bucket_name = "documents"
        self.supabase_url = (settings.supabase_url or "").rstrip("/")
        self.service_role_key = settings.supabase_service_role_key or ""

    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.service_role_key)

    def upload_document(
        self,
        user_id: str,
        document_id: str,
        filename: str,
        file_bytes: bytes,
        file_type: str,
    ) -> str:
        if not self.is_configured():
            raise RuntimeError("Supabase Storage is not configured.")

        try:
            from supabase import create_client
        except (
            ImportError
        ) as exc:  # pragma: no cover - dependency installed during setup
            raise RuntimeError("The Supabase Python client is not installed.") from exc

        client = create_client(self.supabase_url, self.service_role_key)
        storage_path = f"{user_id}/{document_id}/{filename}"
        content_type = (
            "application/pdf"
            if file_type == "pdf"
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        client.storage.from_(self.bucket_name).upload(
            storage_path,
            file_bytes,
            {"content-type": content_type, "upsert": "true"},
        )

        return storage_path
