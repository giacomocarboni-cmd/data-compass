"""
API-key routing by tier — Phase 6, Step 6.4.

Resolves *which* Anthropic key a query should use, based on the current
session's tier:

  * public    → the visitor's own BYOK key (session-only, never the owner key)
  * admin     → the owner key from configuration
  * recruiter → the owner key from configuration

The owner key is therefore never exposed to anonymous/public visitors; they must
bring their own. Logged-in tiers transparently use the owner key so a recruiter
can try the app without a key of their own (their usage is capped by the
recruiter quota, Step 6.3).

Tier state lives in Streamlit session state under ``auth_tier`` and is set by the
login UI (Step 6.5). The functions accept a plain dict so they are testable
without a running Streamlit server.
"""
from __future__ import annotations

from dataclasses import dataclass

from data_compass.auth.api_key import get_key
from data_compass import config

TIER_PUBLIC = "public"
TIER_ADMIN = "admin"
TIER_RECRUITER = "recruiter"

_LOGGED_IN_TIERS = frozenset({TIER_ADMIN, TIER_RECRUITER})

_TIER_KEY = "auth_tier"
_RECRUITER_TOKEN_ID = "auth_recruiter_token_id"
_USERNAME_KEY = "auth_username"


@dataclass
class KeyResolution:
    """The resolved key and where it came from."""
    key: str | None
    source: str  # 'byok' | 'owner' | 'none'
    tier: str


# ---------------------------------------------------------------------------
# Session tier state
# ---------------------------------------------------------------------------

def get_tier(session: dict) -> str:
    """Return the session's tier (defaults to public)."""
    return session.get(_TIER_KEY, TIER_PUBLIC)


def is_logged_in(session: dict) -> bool:
    """Return True if the session is an admin or recruiter."""
    return get_tier(session) in _LOGGED_IN_TIERS


def login_admin(session: dict, username: str) -> None:
    """Mark the session as an authenticated admin."""
    session[_TIER_KEY] = TIER_ADMIN
    session[_USERNAME_KEY] = username
    session.pop(_RECRUITER_TOKEN_ID, None)


def login_recruiter(session: dict, token_id: int) -> None:
    """Mark the session as an authenticated recruiter, recording the token id."""
    session[_TIER_KEY] = TIER_RECRUITER
    session[_RECRUITER_TOKEN_ID] = token_id
    session.pop(_USERNAME_KEY, None)


def get_recruiter_token_id(session: dict) -> int | None:
    """Return the logged-in recruiter's token id, or None."""
    return session.get(_RECRUITER_TOKEN_ID)


def logout(session: dict) -> None:
    """Drop all auth state, returning the session to the public tier."""
    for k in (_TIER_KEY, _RECRUITER_TOKEN_ID, _USERNAME_KEY):
        session.pop(k, None)


# ---------------------------------------------------------------------------
# Key resolution
# ---------------------------------------------------------------------------

def get_upload_scope(session: dict) -> str:
    """Return a login-scoped cache key for uploaded dataset queries.

    Uploaded dataset cache entries must never be shared between users, so
    we use a tier-qualified identifier as the scope rather than "public".
    """
    tier = get_tier(session)
    if tier == TIER_ADMIN:
        return f"upload:admin:{session.get(_USERNAME_KEY, 'admin')}"
    if tier == TIER_RECRUITER:
        return f"upload:recruiter:{session.get(_RECRUITER_TOKEN_ID, '0')}"
    return "upload:public"


def resolve_api_key(
    session: dict,
    *,
    owner_key: str | None = None,
) -> KeyResolution:
    """Resolve the Anthropic key for the current tier.

    ``owner_key`` may be injected (used in tests); when omitted it is read from
    ``config.OWNER_API_KEY`` at call time.
    """
    tier = get_tier(session)

    if tier in _LOGGED_IN_TIERS:
        key = owner_key if owner_key is not None else config.OWNER_API_KEY
        key = key.strip() if key else ""
        return KeyResolution(key or None, "owner" if key else "none", tier)

    # Public tier → BYOK
    byok = get_key(session)
    byok = byok.strip() if byok else ""
    return KeyResolution(byok or None, "byok" if byok else "none", tier)
