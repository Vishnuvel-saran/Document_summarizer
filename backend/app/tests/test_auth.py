from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt

from app.auth import verify_supabase_token


def test_verify_supabase_token_accepts_valid_jwt_with_jwks(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    payload = {
        "sub": "user-123",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, "test-secret", algorithm="HS256")

    signing_key = MagicMock()
    signing_key.key = "public-key"

    with (
        patch("app.auth.jwt.PyJWKClient") as mock_client,
        patch(
            "app.auth.jwt.decode",
            return_value=payload,
        ),
    ):
        mock_client.return_value.get_signing_key_from_jwt.return_value = signing_key

        assert verify_supabase_token(token)["sub"] == "user-123"


def test_verify_supabase_token_rejects_invalid_jwt(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    with patch("app.auth.jwt.PyJWKClient") as mock_client:
        mock_client.return_value.get_signing_key_from_jwt.side_effect = jwt.PyJWTError(
            "bad key"
        )

        try:
            verify_supabase_token("not-a-valid-jwt")
            assert False, "Expected ValueError for invalid JWT."
        except ValueError:
            pass
