import logging
import os
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


def _verify_legacy_token(token: str, secret: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"require": ["sub", "exp"]},
    )

    if not payload.get("sub"):
        raise ValueError("JWT missing subject claim.")

    return payload


def _verify_jwks_token(token: str) -> dict[str, Any]:
    supabase_url = (os.getenv("SUPABASE_URL") or settings.supabase_url or "").rstrip(
        "/"
    )
    if not supabase_url:
        raise ValueError("SUPABASE_URL is not configured.")

    jwks_uri = f"{supabase_url}/auth/v1/.well-known/jwks.json"
    issuer = f"{supabase_url}/auth/v1"

    try:
        signing_key = jwt.PyJWKClient(jwks_uri).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            issuer=issuer,
            options={"require": ["sub", "exp"]},
        )
    except jwt.PyJWTError as exc:  # pragma: no cover - exercised via direct tests
        logger.warning("Supabase JWT validation failed: %s", type(exc).__name__)
        raise ValueError("Invalid or expired JWT.") from exc

    if not payload.get("sub"):
        raise ValueError("JWT missing subject claim.")

    return payload


def verify_supabase_token(token: str) -> dict[str, Any]:
    secret = os.getenv("SUPABASE_JWT_SECRET") or settings.supabase_jwt_secret

    if secret:
        try:
            return _verify_legacy_token(token, secret)
        except jwt.PyJWTError:
            pass

    return _verify_jwks_token(token)


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
