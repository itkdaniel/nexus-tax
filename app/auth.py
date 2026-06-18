"""
JWT authentication helpers for nexus-tax.

Accepts HMAC-SHA256 JWT tokens issued by the main NexusConsult portfolio
(server/auth.ts). The secret must match JWT_SECRET in both services.

Middleware:
  - require_admin: 401/403 if token missing or role != "admin"
  - optional_admin: extracts user info if present, does not block
"""
from __future__ import annotations

import hmac
import base64
import hashlib
import json
import time
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_settings = None
_bearer = HTTPBearer(auto_error=False)


def configure_auth(settings) -> None:
    """Wire auth to the injected settings (called from create_app lifespan)."""
    global _settings
    _settings = settings


def _get_settings():
    global _settings
    if _settings is None:
        from app.config import get_settings
        _settings = get_settings()
    return _settings


def _decode_jwt(token: str) -> dict:
    """
    Decode and verify an HMAC-SHA256 JWT.
    Raises ValueError if signature invalid or expired.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Malformed JWT")
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"

        settings = _get_settings()
        expected_sig = hmac.new(
            settings.jwt_secret.encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).digest()
        expected_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode()

        if not hmac.compare_digest(sig_b64, expected_b64):
            raise ValueError("Invalid signature")

        # Decode payload
        padded = payload_b64 + "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        # Check expiry
        if "exp" in payload and payload["exp"] < int(time.time()):
            raise ValueError("Token expired")

        return payload
    except (ValueError, KeyError, UnicodeDecodeError):
        raise
    except Exception as exc:
        raise ValueError(f"JWT decode error: {exc}") from exc


async def require_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """FastAPI dependency — requires a valid admin JWT."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Missing authorization token", "code": "MISSING_TOKEN", "details": {}, "request_id": ""},
        )
    try:
        payload = _decode_jwt(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": str(exc), "code": "INVALID_TOKEN", "details": {}, "request_id": ""},
        )
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "Admin role required", "code": "FORBIDDEN", "details": {}, "request_id": ""},
        )
    return payload
