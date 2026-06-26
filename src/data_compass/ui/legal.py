"""
Legal surfaces — Phase 8, Step 8.5.

Three pieces:
  * render_tos_gate()       — blocks the upload journey until the user accepts
                              the Terms of Use (no-real-personal-data warranty +
                              indemnity). Acceptance is held in session state.
  * render_privacy_notice() — an in-app Privacy Notice (controller, AI
                              sub-processor, caching, ICO route), shown inside
                              an expander on the ToS gate so it is reachable
                              from the UI.
  * render_caching_warning()— a short caching caption shown to all tiers on the
                              query panel.

The text is DRAFT, sourced from the locale file (British English). The
canonical, fuller notice lives in docs/PRIVACY_NOTICE.md, to be reviewed before
public deployment.

Public API
----------
TOS_ACCEPTED_KEY   session key for ToS acceptance
render_tos_gate() -> bool       True once accepted (safe to proceed)
render_privacy_notice() -> None
render_caching_warning() -> None
"""
from __future__ import annotations

import streamlit as st

from data_compass.i18n import t

TOS_ACCEPTED_KEY = "tos_accepted"


def _accept_tos() -> None:
    st.session_state[TOS_ACCEPTED_KEY] = True


def render_privacy_notice() -> None:
    """Render the in-app Privacy Notice (key points, from locale)."""
    st.subheader(t("legal.privacy_header"))
    st.write(t("legal.privacy_controller"))
    st.write(t("legal.privacy_pii"))
    st.write(t("legal.privacy_subprocessor"))
    st.write(t("legal.privacy_caching"))
    st.write(t("legal.privacy_rights"))


def render_caching_warning() -> None:
    """Short caching caption — shown to all tiers wherever queries run."""
    st.caption(t("legal.caching_warning"))


def render_tos_gate() -> bool:
    """Block the upload journey until the Terms of Use are accepted.

    Returns True once accepted. While not accepted, renders the terms, an
    expander containing the Privacy Notice, an acceptance checkbox and an
    "Accept and continue" button, and returns False.
    """
    if st.session_state.get(TOS_ACCEPTED_KEY):
        return True

    st.subheader(t("legal.tos_header"))
    st.caption(t("legal.tos_draft_note"))
    st.write(t("legal.tos_intro"))
    st.write(t("legal.tos_warranty"))
    st.write(t("legal.tos_indemnity"))

    with st.expander(t("legal.privacy_expander")):
        render_privacy_notice()

    agreed = st.checkbox(t("legal.tos_accept_checkbox"), key="_tos_checkbox")
    st.button(
        t("legal.tos_accept_button"),
        on_click=_accept_tos,
        disabled=not agreed,
        type="primary",
        key="tos_accept_button",
    )
    if not agreed:
        st.info(t("legal.tos_required"))
    return False
