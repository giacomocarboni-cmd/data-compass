"""
Login UI — Phase 6, Step 6.5.

Renders the "Account" panel: when logged out, an administrator (username +
password) and a recruiter (access token) login form; when logged in, the current
identity, remaining recruiter quota, and a log-out button. Tier state is written
to ``st.session_state`` via ``auth.key_router`` and consumed by the query flow's
key routing and quota gate.

Login/logout are handled in ``on_click`` callbacks (which run before the script
re-executes) rather than checking a button's return value and calling
``st.rerun()``. This keeps the rendered view consistent within a single run and
behaves cleanly under Streamlit's AppTest harness.

Kept out of the sidebar deliberately so the query view's widget layout (and the
existing AppTests that target it) is unaffected.
"""
from __future__ import annotations

import streamlit as st

from data_compass.auth import key_router, policy, recruiter, store
from data_compass.auth import resource as auth_resource
from data_compass.config import ADMIN_PASSWORD_MAX_AGE_DAYS
from data_compass.i18n import t

_ERROR_FLAG = "_auth_error"
_SUCCESS_FLAG = "_auth_success"


def purge_expired_recruiter_uploads(session) -> None:
    """Remove a recruiter's uploaded datasets once their login has expired.

    A recruiter token is gated on both time (expires_at, ~30 days) and a query
    cap (~20). When either limit is reached the in-memory uploaded datasets are
    dropped. The session deliberately stays logged in, so the query gate can
    still show the precise expiry/quota message rather than a generic one.

    No-op unless the session is currently a recruiter, so uploads already
    removed by an explicit logout are never removed twice ("unless already
    removed by the login").
    """
    if key_router.get_tier(session) != key_router.TIER_RECRUITER:
        return

    conn = auth_resource.get_auth_conn()
    token_id = key_router.get_recruiter_token_id(session)
    token = recruiter.get_token(conn, token_id) if token_id is not None else None
    access = recruiter.check_access(token) if token is not None else None
    if token is not None and access is not None and access.allowed:
        return  # still valid — leave the uploaded datasets intact

    from data_compass.ui.upload import clear_uploaded_datasets

    clear_uploaded_datasets(session)


def render_account_panel() -> None:
    """Render the Account panel in the main content area."""
    st.header(t("auth.panel_header"))

    session = st.session_state
    tier = key_router.get_tier(session)

    if tier == key_router.TIER_ADMIN:
        _render_admin_status(session)
        return
    if tier == key_router.TIER_RECRUITER:
        _render_recruiter_status(session)
        return

    _render_public_login(session)


# ---------------------------------------------------------------------------
# Logged-in views
# ---------------------------------------------------------------------------

def _render_admin_status(session) -> None:
    _flash_success(session)
    st.success(t("auth.status_admin"))
    if session.get("_admin_renewal_due"):
        st.warning(
            t("auth.password_renewal_due").format(days=ADMIN_PASSWORD_MAX_AGE_DAYS)
        )
    st.button(t("auth.logout_button"), key="logout_btn", on_click=_cb_logout)


def _render_recruiter_status(session) -> None:
    _flash_success(session)
    conn = auth_resource.get_auth_conn()
    token_id = key_router.get_recruiter_token_id(session)
    token = recruiter.get_token(conn, token_id) if token_id is not None else None
    if token is not None:
        access = recruiter.check_access(token)
        st.success(
            t("auth.status_recruiter").format(
                remaining=access.remaining, cap=token.query_cap
            )
        )
    st.button(t("auth.logout_button"), key="logout_btn", on_click=_cb_logout)


# ---------------------------------------------------------------------------
# Logged-out (public) view
# ---------------------------------------------------------------------------

def _render_public_login(session) -> None:
    st.info(t("auth.status_public"))
    st.subheader(t("auth.login_header"))

    error = session.pop(_ERROR_FLAG, None)
    if error:
        st.error(error)

    # --- Recruiter (access token) ---------------------------------------
    st.markdown(f"**{t('auth.recruiter_subheader')}**")
    st.text_input(
        label=t("auth.recruiter_token_label"),
        type="password",
        help=t("auth.recruiter_token_help"),
        key="_recruiter_token",
    )
    st.button(
        t("auth.recruiter_login_button"),
        key="recruiter_login_btn",
        on_click=_cb_recruiter_login,
    )

    st.divider()

    # --- Administrator (username + password) -----------------------------
    st.markdown(f"**{t('auth.admin_subheader')}**")
    st.text_input(t("auth.admin_username_label"), key="_admin_user")
    st.text_input(t("auth.admin_password_label"), type="password", key="_admin_pass")
    st.button(
        t("auth.admin_login_button"),
        key="admin_login_btn",
        on_click=_cb_admin_login,
    )


# ---------------------------------------------------------------------------
# Callbacks (run before the next script execution)
# ---------------------------------------------------------------------------

def _cb_recruiter_login() -> None:
    session = st.session_state
    token_value = (session.get("_recruiter_token") or "").strip()
    if not token_value:
        session[_ERROR_FLAG] = t("auth.token_invalid")
        return
    conn = auth_resource.get_auth_conn()
    token = recruiter.verify_token(conn, token_value)
    if token is None:
        session[_ERROR_FLAG] = t("auth.token_invalid")
        return
    access = recruiter.check_access(token)
    if not access.allowed:
        session[_ERROR_FLAG] = _token_block_message(access.reason)
        return
    key_router.login_recruiter(session, token.id)
    session[_SUCCESS_FLAG] = t("auth.login_success_recruiter")


def _cb_admin_login() -> None:
    session = st.session_state
    username = (session.get("_admin_user") or "").strip()
    password = session.get("_admin_pass") or ""
    conn = auth_resource.get_auth_conn()
    user = store.authenticate(conn, username, password)
    if user is None:
        session[_ERROR_FLAG] = t("auth.login_failed")
        return
    key_router.login_admin(session, user.username)
    session["_admin_renewal_due"] = policy.must_change_password(user)
    session[_SUCCESS_FLAG] = t("auth.login_success_admin")


def _cb_logout() -> None:
    # Logging out removes the session's uploaded datasets before dropping the
    # tier, so an expiry check later finds nothing left to remove.
    from data_compass.ui.upload import clear_uploaded_datasets

    clear_uploaded_datasets(st.session_state)
    key_router.logout(st.session_state)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flash_success(session) -> None:
    msg = session.pop(_SUCCESS_FLAG, None)
    if msg:
        st.success(msg)


def _token_block_message(reason: str) -> str:
    return {
        "expired": t("auth.token_expired"),
        "quota_exceeded": t("auth.token_quota"),
        "inactive": t("auth.token_inactive"),
    }.get(reason, t("auth.token_invalid"))
