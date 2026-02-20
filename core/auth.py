"""
backend/core/auth.py
PATCH 11 — JWT Expiry Enforcement
Advanced JWT verification with expiry enforcement, rotation detection,
token blacklisting, and detailed audit logging.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Optional

import jwt
from jwt.exceptions import (
    DecodeError,
    ExpiredSignatureError,
    ImmatureSignatureError,
    InvalidAlgorithmError,
    InvalidAudienceError,
    InvalidIssuedAtError,
    InvalidIssuerError,
    MissingRequiredClaimError,
)

from backend.core.config import settings
from backend.core.exceptions import (
    AuthenticationError,
    TokenBlacklistedError,
    TokenExpiredError,
    TokenInvalidError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory token blacklist (swap for Redis in production)
# ---------------------------------------------------------------------------
_blacklist: set[str] = set()


def blacklist_token(jti: str) -> None:
    """Revoke a token by its JWT ID (jti claim)."""
    _blacklist.add(jti)
    logger.info("Token blacklisted | jti=%s", jti)


def is_blacklisted(jti: str) -> bool:
    return jti in _blacklist


# ---------------------------------------------------------------------------
# Core decode helper
# ---------------------------------------------------------------------------

_REQUIRED_CLAIMS = frozenset({"sub", "iat", "exp", "jti"})

_DECODE_OPTIONS: dict[str, Any] = {
    "verify_exp": True,       # Enforce expiry — PATCH 11 requirement
    "verify_iat": True,       # Reject tokens with future iat
    "verify_nbf": True,       # Honour not-before if present
    "verify_aud": bool(getattr(settings, "JWT_AUDIENCE", None)),
    "require": list(_REQUIRED_CLAIMS),
}


def _decode_token(token: str) -> dict[str, Any]:
    """
    Low-level JWT decode with full claim verification.

    Raises a domain-specific exception for every failure mode so callers
    never need to import jwt themselves.
    """
    decode_kwargs: dict[str, Any] = {
        "algorithms": ["HS256"],
        "options": _DECODE_OPTIONS,
    }
    if getattr(settings, "JWT_AUDIENCE", None):
        decode_kwargs["audience"] = settings.JWT_AUDIENCE
    if getattr(settings, "JWT_ISSUER", None):
        decode_kwargs["issuer"] = settings.JWT_ISSUER

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET,
            **decode_kwargs,
        )
    except ExpiredSignatureError as exc:
        logger.warning("JWT expired | detail=%s", exc)
        raise TokenExpiredError("Access token has expired. Please refresh.") from exc
    except ImmatureSignatureError as exc:
        logger.warning("JWT not yet valid | detail=%s", exc)
        raise TokenInvalidError("Token is not yet valid (nbf).") from exc
    except InvalidIssuedAtError as exc:
        logger.warning("JWT invalid iat | detail=%s", exc)
        raise TokenInvalidError("Token issued-at claim is invalid.") from exc
    except InvalidAudienceError as exc:
        logger.warning("JWT audience mismatch | detail=%s", exc)
        raise TokenInvalidError("Token audience is invalid.") from exc
    except InvalidIssuerError as exc:
        logger.warning("JWT issuer mismatch | detail=%s", exc)
        raise TokenInvalidError("Token issuer is invalid.") from exc
    except MissingRequiredClaimError as exc:
        logger.warning("JWT missing claim | detail=%s", exc)
        raise TokenInvalidError(f"Token is missing required claim: {exc}") from exc
    except InvalidAlgorithmError as exc:
        logger.warning("JWT algorithm violation | detail=%s", exc)
        raise TokenInvalidError("Token algorithm is not permitted.") from exc
    except DecodeError as exc:
        logger.warning("JWT decode error | detail=%s", exc)
        raise TokenInvalidError("Token could not be decoded.") from exc

    return payload


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify_jwt(token: str) -> dict[str, Any]:
    """
    Fully verify a JWT access token.

    Steps
    -----
    1. Decode and verify signature, expiry, iat, nbf, aud, iss.
    2. Confirm required claims are present.
    3. Check the token's jti against the revocation blacklist.
    4. Emit a structured audit log entry on success.

    Returns the decoded payload dict on success.
    Raises TokenExpiredError, TokenBlacklistedError, or TokenInvalidError
    on any failure.
    """
    if not token or not isinstance(token, str):
        raise TokenInvalidError("Token must be a non-empty string.")

    payload = _decode_token(token)  # raises on any JWT failure

    jti: Optional[str] = payload.get("jti")
    if jti and is_blacklisted(jti):
        logger.warning(
            "Blacklisted token used | jti=%s sub=%s",
            jti,
            payload.get("sub"),
        )
        raise TokenBlacklistedError("Token has been revoked.")

    _audit_success(payload)
    return payload


def verify_jwt_optional(token: Optional[str]) -> Optional[dict[str, Any]]:
    """
    Like verify_jwt() but returns None when no token is supplied.
    Useful for endpoints that allow anonymous and authenticated access.
    """
    if token is None:
        return None
    return verify_jwt(token)


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def require_jwt(f):
    """
    Route decorator that extracts and validates a Bearer token from
    the `Authorization` header (framework-agnostic helper).

    Usage (Flask example):
        @app.route("/protected")
        @require_jwt
        def protected(jwt_payload):
            return jsonify(jwt_payload)
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        # Import lazily to keep this module framework-agnostic.
        try:
            from flask import request  # type: ignore[import]
            auth_header: str = request.headers.get("Authorization", "")
        except ImportError:
            raise RuntimeError(
                "require_jwt decorator requires Flask. "
                "Inject jwt_payload manually for other frameworks."
            )

        scheme, _, token = auth_header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AuthenticationError("Missing or malformed Authorization header.")

        payload = verify_jwt(token)
        return f(*args, jwt_payload=payload, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _audit_success(payload: dict[str, Any]) -> None:
    exp_ts = payload.get("exp", 0)
    expires_in = max(0, exp_ts - int(time.time()))
    logger.info(
        "JWT verified | sub=%s jti=%s expires_in=%ds issued_at=%s",
        payload.get("sub"),
        payload.get("jti"),
        expires_in,
        _fmt_ts(payload.get("iat")),
    )


def _fmt_ts(ts: Optional[int]) -> str:
    if ts is None:
        return "n/a"
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return str(ts)