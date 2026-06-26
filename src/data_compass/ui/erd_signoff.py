"""
ERD sign-off UI — Phase 7, Step 7.4.

render_erd_signoff() presents:
  1. Structural validation results (deterministic issues from validate_erd).
  2. An optional AI plausibility check (Haiku, on demand).
  3. Per-suggestion Accept / Keep-original buttons (default: keep).
  4. A "Sign off ERD" button that stores the final ERDDeclaration in
     session_state["erd_signed_off"].

All Haiku calls are mocked in tests; no live API calls during testing.

Session-state keys consumed:
  erd_declaration     ERDDeclaration (written by relationships.py step 7.2)
  erd_validation      ERDValidationResult (written by upload.py after 7.3)
Session-state keys written:
  _plausibility_suggestions  list[PlausibilitySuggestion]
  _plausibility_accepted     set[int]
  erd_signed_off             ERDDeclaration (after user sign-off)
"""
from __future__ import annotations

import streamlit as st

from data_compass.auth import key_router
from data_compass import config
from data_compass.erd.infer import ERDDeclaration
from data_compass.erd.plausibility import (
    PlausibilitySuggestion,
    apply_decisions,
    check_plausibility,
)
from data_compass.erd.validate import ERDValidationResult
from data_compass.i18n import t

_SUGGESTIONS_KEY = "_plausibility_suggestions"
_ACCEPTED_KEY = "_plausibility_accepted"
SIGNED_OFF_KEY = "erd_signed_off"


def render_erd_signoff(
    declaration: ERDDeclaration,
    validation: ERDValidationResult,
) -> None:
    """Render the ERD review and sign-off panel."""
    st.divider()
    st.subheader(t("erd_signoff.header"))

    # -----------------------------------------------------------------------
    # Already signed off — just confirm and exit
    # -----------------------------------------------------------------------
    if st.session_state.get(SIGNED_OFF_KEY) is not None:
        st.success(t("erd_signoff.already_signed_off"))
        return

    # -----------------------------------------------------------------------
    # 1. Structural validation results
    # -----------------------------------------------------------------------
    st.markdown(f"**{t('erd_signoff.validation_header')}**")
    if validation.is_valid:
        st.success(t("erd_signoff.no_issues"))
    else:
        for issue in validation.issues:
            st.warning(issue.detail)

    # -----------------------------------------------------------------------
    # 2. AI plausibility check (on demand)
    # -----------------------------------------------------------------------
    st.divider()
    suggestions: list[PlausibilitySuggestion] = st.session_state.get(
        _SUGGESTIONS_KEY, []
    )
    accepted: set[int] = st.session_state.setdefault(_ACCEPTED_KEY, set())

    if not suggestions and _SUGGESTIONS_KEY not in st.session_state:
        if st.button(t("erd_signoff.ai_check_button"), key="run_plausibility_btn"):
            api_key = _resolve_key()
            if api_key:
                with st.spinner(t("erd_signoff.ai_running")):
                    sugs, _ = check_plausibility(api_key, declaration)
                st.session_state[_SUGGESTIONS_KEY] = sugs
                st.rerun()
    else:
        suggestions = st.session_state.get(_SUGGESTIONS_KEY, [])
        if not suggestions:
            st.info(t("erd_signoff.no_suggestions"))
        else:
            st.markdown(f"**{t('erd_signoff.suggestions_header')}**")
            for i, sug in enumerate(suggestions):
                with st.expander(
                    t("erd_signoff.suggestion_label").format(
                        from_table=sug.from_table,
                        from_col=sug.from_col,
                        to_table=sug.to_table,
                        to_col=sug.to_col,
                    )
                ):
                    st.caption(t("erd_signoff.suggestion_reason").format(reason=sug.reason))
                    if sug.suggested_from_col:
                        st.info(
                            t("erd_signoff.suggestion_proposed").format(
                                col=sug.suggested_from_col
                            )
                        )
                    c1, c2 = st.columns(2)
                    is_accepted = i in accepted
                    if c1.button(
                        t("erd_signoff.accept_button"),
                        key=f"accept_sug_{i}",
                        type="primary" if not is_accepted else "secondary",
                        on_click=_cb_accept,
                        args=(i,),
                    ):
                        pass
                    if c2.button(
                        t("erd_signoff.reject_button"),
                        key=f"reject_sug_{i}",
                        on_click=_cb_reject,
                        args=(i,),
                    ):
                        pass

    # -----------------------------------------------------------------------
    # 3. Sign off
    # -----------------------------------------------------------------------
    st.divider()
    if st.button(
        t("erd_signoff.sign_off_button"),
        type="primary",
        key="sign_off_btn",
        on_click=_cb_sign_off,
        args=(declaration, suggestions, accepted),
    ):
        pass

    if st.session_state.get(SIGNED_OFF_KEY) is not None:
        st.success(t("erd_signoff.signed_off"))


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def _cb_accept(index: int) -> None:
    accepted: set[int] = st.session_state.setdefault(_ACCEPTED_KEY, set())
    accepted.add(index)


def _cb_reject(index: int) -> None:
    accepted: set[int] = st.session_state.setdefault(_ACCEPTED_KEY, set())
    accepted.discard(index)


def _cb_sign_off(
    declaration: ERDDeclaration,
    suggestions: list[PlausibilitySuggestion],
    accepted: set[int],
) -> None:
    final = apply_decisions(declaration, suggestions, accepted)
    st.session_state[SIGNED_OFF_KEY] = final


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_key() -> str | None:
    """Return the API key appropriate for the current session tier."""
    from data_compass.auth.key_router import resolve_api_key
    res = resolve_api_key(st.session_state, owner_key=config.OWNER_API_KEY)
    return res.key
