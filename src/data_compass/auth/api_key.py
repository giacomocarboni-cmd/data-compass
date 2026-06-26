"""
BYOK (Bring-Your-Own-Key) API key handling.

The key is stored exclusively in Streamlit session state — a server-side
in-memory dict that is private to the current browser session.  It is never
written to disk, logged, or included in any response body.

The logic functions accept a plain dict so they can be tested without a
running Streamlit server.
"""
from __future__ import annotations

_SESSION_KEY = "byok_api_key"

# Data Compass only calls Anthropic Claude, so a BYOK key must be an Anthropic
# key. All Anthropic keys carry this prefix; keys for other providers (e.g. an
# OpenAI ``sk-...`` / ``sk-proj-...`` key) do not.
_ANTHROPIC_PREFIX = "sk-ant-"


# ---------------------------------------------------------------------------
# Pure logic (testable without Streamlit)
# ---------------------------------------------------------------------------

def is_anthropic_key(key: str | None) -> bool:
    """Return True if the key looks like an Anthropic key (``sk-ant-`` prefix).

    Used to reject another provider's key (e.g. OpenAI) at input time with a
    clear message, rather than storing it and failing later inside the SDK call.
    """
    return bool(key) and key.strip().startswith(_ANTHROPIC_PREFIX)

def set_key(session: dict, key: str) -> None:
    """Store the API key in session state."""
    session[_SESSION_KEY] = key


def get_key(session: dict) -> str | None:
    """Return the stored API key, or None if not set."""
    return session.get(_SESSION_KEY)


def clear_key(session: dict) -> None:
    """Remove the API key from session state."""
    session.pop(_SESSION_KEY, None)


def has_key(session: dict) -> bool:
    """Return True if a non-empty API key is present."""
    k = session.get(_SESSION_KEY)
    return bool(k and k.strip())


# ---------------------------------------------------------------------------
# Streamlit sidebar widget
# ---------------------------------------------------------------------------

def render_sidebar_key_input() -> str | None:
    """
    Render a password input for the BYOK key in the Streamlit sidebar.
    Returns the current key value (may be None if not entered).
    """
    import streamlit as st
    from data_compass.i18n import t

    value = st.text_input(
        label=t("sidebar.api_key_label"),
        type="password",
        placeholder="sk-ant-...",
        help=t("sidebar.api_key_help"),
        key="_byok_input",
    )

    raw = value.strip() if value else ""
    if raw:
        if is_anthropic_key(raw):
            set_key(st.session_state, raw)
            st.caption(f":green[{t('sidebar.api_key_set')}]")
        else:
            # Another provider's key — don't store it; guide the user.
            clear_key(st.session_state)
            st.caption(f":red[{t('sidebar.api_key_wrong_provider')}]")
    elif not has_key(st.session_state):
        st.caption(t("sidebar.api_key_not_set"))

    return get_key(st.session_state)
