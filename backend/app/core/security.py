import logging
import time

import httpx
import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

# Small in-process cache so a single user refreshing a page does not
# fan out into N external calls when their token is Supabase-signed.
# Keyed by token; stores (expires_at_monotonic, payload_dict).
_supabase_cache: dict[str, tuple[float, dict]] = {}
_SUPABASE_CACHE_TTL_SECONDS = 60.0
_SUPABASE_CACHE_MAX_ENTRIES = 512


def _cache_get(token: str) -> dict | None:
    entry = _supabase_cache.get(token)
    if entry is None:
        return None
    expires_at, payload = entry
    if time.monotonic() > expires_at:
        _supabase_cache.pop(token, None)
        return None
    return payload


def _cache_put(token: str, payload: dict) -> None:
    if len(_supabase_cache) >= _SUPABASE_CACHE_MAX_ENTRIES:
        _supabase_cache.pop(next(iter(_supabase_cache)), None)
    _supabase_cache[token] = (time.monotonic() + _SUPABASE_CACHE_TTL_SECONDS, payload)


def _validate_via_supabase(token: str) -> dict | None:
    """Fallback: validate a Supabase-issued token by calling GET /auth/v1/user.

    Used when the local JWT secret does not match the Supabase project's
    signing secret (e.g. after key rotation or in environments where the
    secret is not configured). Returns a payload-shaped dict on success.

    The call is synchronous but FastAPI dispatches non-async dependencies on
    a threadpool, so this will not block the event loop.
    """
    cached = _cache_get(token)
    if cached is not None:
        return cached
    supabase_url = getattr(settings, "SUPABASE_URL", None)
    if not supabase_url:
        return None
    try:
        resp = httpx.get(
            f"{supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.SUPABASE_SERVICE_ROLE_KEY or "",
            },
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("Supabase token validation failed: %s", exc)
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    payload = {
        "sub": data.get("id"),
        "email": data.get("email"),
        "aud": data.get("aud", "authenticated"),
        "role": data.get("role", "authenticated"),
    }
    _cache_put(token, payload)
    return payload


def decode_access_token(token: str) -> dict | None:
    # ``JWT_SECRET_KEY`` is optional at boot now (preview deployments may not
    # have the full env-var set — see ``Settings.runtime_ready_errors()``).
    # When it's missing we still attempt the Supabase fallback so a degraded
    # deployment can prove a token at all if SUPABASE_URL happens to be set;
    # otherwise the caller treats ``None`` as a 401, which is the correct
    # response on an unconfigured environment.
    secret = settings.JWT_SECRET_KEY
    if secret is None:
        return _validate_via_supabase(token)
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=[settings.JWT_ALGORITHM],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired")
        return None
    except jwt.InvalidAudienceError:
        logger.warning("JWT token has invalid audience")
        return None
    except jwt.InvalidSignatureError:
        return _validate_via_supabase(token)
    except jwt.PyJWTError as exc:
        logger.warning("JWT decode failed: %s", exc)
        return None
