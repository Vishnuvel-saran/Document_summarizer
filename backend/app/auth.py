import os
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

security = HTTPBearer(auto_error=False)


def verify_supabase_token(token: str) -> dict[str, Any]:
    secret = os.getenv("SUPABASE_JWT_SECRET", settings.supabase_jwt_secret)
    if not secret:
        raise ValueError("SUPABASE_JWT_SECRET is not configured.")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError as exc:  # pragma: no cover - exercised via direct tests
        raise ValueError("Invalid or expired JWT.") from exc

    if not payload.get("sub"):
        raise ValueError("JWT missing subject claim.")

    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
        )

    try:
        return verify_supabase_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
