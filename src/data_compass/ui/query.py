"""
Query panel and BYOK sidebar widget — Phases 4–6.

render_api_key_sidebar()      — password input in sidebar; stores key in session state.
render_query_panel(dataset_id) — question input, Ask button, tier-aware key routing
                                 and recruiter quota gating, delegates to results.py.
"""
from __future__ import annotations

import streamlit as st

from data_compass.auth import key_router, recruiter
from data_compass.auth import resource as auth_resource
from data_compass.auth.api_key import clear_key, get_key, has_key, is_anthropic_key, set_key
from data_compass import config
from data_compass.i18n import t
from data_compass.ui.results import render_results

_BYOK_KEY = "byok_api_key"
_RESULT_KEY = "query_result"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_api_key_sidebar() -> str | None:
    """Render the BYOK API-key password input in the sidebar.

    Returns the active key (str) or None if none is set.
    """
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
            # Another provider's key (e.g. OpenAI) — don't store it; guide the user.
            clear_key(st.session_state)
            st.caption(f":red[{t('sidebar.api_key_wrong_provider')}]")
    elif not has_key(st.session_state):
        st.caption(t("sidebar.api_key_not_set"))

    return get_key(st.session_state)


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

_BLOCK_MESSAGE_KEYS = {
    "blocked:quota_exceeded": "query.blocked_quota",
    "blocked:expired": "query.blocked_expired",
    "blocked:inactive": "query.blocked_inactive",
    "access_revoked": "query.blocked_inactive",
}


def _render_blocked(result) -> None:
    """Render a gating-blocked query result (no SQL, no API call was made)."""
    if result.error == "no_key":
        return  # handled upstream before the query was attempted
    st.error(t(_BLOCK_MESSAGE_KEYS.get(result.error, "query.blocked_generic")))


def _render_recruiter_quota(session) -> None:
    """Show the recruiter's remaining-query caption above the input."""
    conn = auth_resource.get_auth_conn()
    token_id = key_router.get_recruiter_token_id(session)
    token = recruiter.get_token(conn, token_id) if token_id is not None else None
    if token is None:
        return
    access = recruiter.check_access(token)
    st.caption(
        t("query.recruiter_quota").format(
            remaining=access.remaining, cap=token.query_cap
        )
    )


_UPLOAD_CONN_KEY = "_uploaded_duckdb_conn"


def render_query_panel(dataset_id: str | None = None) -> None:
    """Render the NL→SQL query input and results panel."""
    from data_compass.cache import resource
    from data_compass.core.query_flow import run_gated_query, QueryResult
    from data_compass.ui.dataset_browser import _cached_load

    st.header(t("query.header"))

    from data_compass.ui.legal import render_caching_warning
    render_caching_warning()

    session = st.session_state

    # ------------------------------------------------------------------
    # Uploaded-data toggle (only available to logged-in users with a
    # signed-off ERD)
    # ------------------------------------------------------------------
    signed_off = session.get("erd_signed_off")
    stored_files = session.get("uploaded_files", [])
    use_upload = False

    if signed_off and stored_files and key_router.is_logged_in(session):
        use_upload = st.checkbox(
            t("query.use_uploaded_data"),
            key="use_uploaded_data_toggle",
        )

    # ------------------------------------------------------------------
    # Resolve connection, schema_text, dataset_id, and scope
    # ------------------------------------------------------------------
    if use_upload:
        conn = _get_or_create_upload_conn(stored_files)
        schema_text = _build_upload_schema_text(conn, signed_off)
        active_dataset_id = "uploaded"
        scope = key_router.get_upload_scope(session)
    elif dataset_id:
        conn = _cached_load(dataset_id)
        schema_text = None  # built inside run_query from the registry
        active_dataset_id = dataset_id
        scope = "public"
    else:
        st.warning(t("query.no_dataset_warning"))
        return

    resolution = key_router.resolve_api_key(session, owner_key=config.OWNER_API_KEY)

    if resolution.key is None:
        if key_router.is_logged_in(session):
            st.warning(t("query.owner_key_missing"))
        else:
            st.warning(t("query.no_key_warning"))
        return

    if resolution.tier == key_router.TIER_RECRUITER:
        _render_recruiter_quota(session)

    # Question input
    question = st.text_area(
        label=t("query.input_label"),
        placeholder=t("query.input_placeholder"),
        height=80,
        key="question_input",
    )

    if st.button(t("query.submit_button"), type="primary", key="ask_button"):
        if question and question.strip():
            with st.spinner(t("query.running")):
                cache_conn = resource.get_cache_conn()
                auth_conn = (
                    auth_resource.get_auth_conn()
                    if resolution.tier == key_router.TIER_RECRUITER
                    else None
                )
                result: QueryResult = run_gated_query(
                    session, auth_conn, question.strip(), active_dataset_id,
                    conn, cache_conn,
                    owner_key=config.OWNER_API_KEY,
                    scope=scope,
                    schema_text=schema_text,
                )
            st.session_state[_RESULT_KEY] = result

    result = st.session_state.get(_RESULT_KEY)
    if result is not None:
        if getattr(result, "cache_tier", None) == "blocked":
            _render_blocked(result)
        else:
            render_results(result)


def _get_or_create_upload_conn(stored_files):
    """Return (or create) the session-cached DuckDB connection for uploaded files."""
    import duckdb
    from data_compass.data.loader import load_uploaded_dataset
    conn = st.session_state.get(_UPLOAD_CONN_KEY)
    if conn is None or not isinstance(conn, duckdb.DuckDBPyConnection):
        conn = load_uploaded_dataset(stored_files)
        st.session_state[_UPLOAD_CONN_KEY] = conn
    return conn


def _build_upload_schema_text(conn, erd_declaration) -> str:
    """Build schema text from the uploaded DuckDB connection + ERD declaration."""
    from data_compass.data.loader import get_schema
    from data_compass.llm.sql_prompt import build_schema_text_from_erd
    schema = get_schema(conn)
    return build_schema_text_from_erd(schema, erd_declaration, t("query.uploaded_dataset_name"))
