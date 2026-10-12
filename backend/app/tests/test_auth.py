from datetime import datetime, timedelta, timezone

import jwt

from app.auth import verify_supabase_token


def test_verify_supabase_token_accepts_valid_jwt(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")

    payload = {
        "sub": "user-123",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    token = jwt.encode(payload, "test-secret", algorithm="HS256")

    assert verify_supabase_token(token)["sub"] == "user-123"


def test_verify_supabase_token_rejects_invalid_jwt(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")

    try:
        verify_supabase_token("not-a-valid-jwt")
        assert False, "Expected ValueError for invalid JWT."
    except ValueError:
        pass
