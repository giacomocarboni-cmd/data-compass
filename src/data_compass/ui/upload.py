"""
Upload panel — Phase 7, Steps 7.1–7.4.

render_upload_panel() orchestrates the full upload journey for logged-in
users:
  Step 7.1  File uploader (CSV/XLSX, max 3) → session_state["uploaded_files"]
  Step 7.2  Schema infer + PK/FK declaration → session_state["erd_declaration"]
  Step 7.3  Deterministic validation → session_state["erd_validation"]
  Step 7.4  Haiku plausibility + sign-off → session_state["erd_signed_off"]

Once files are parsed they remain in session_state so navigation away and
back does not require re-uploading.  Uploading new files clears all ERD
state for a fresh start.
"""
from __future__ import annotations

import streamlit as st

from data_compass.auth import key_router
from data_compass.erd.infer import TableSchema, infer_schema, table_name_from_filename
from data_compass.erd.validate import validate_erd
from data_compass.i18n import t
from data_compass.ui.erd_signoff import render_erd_signoff
from data_compass.ui.legal import render_tos_gate
from data_compass.ui.pii_gate import (
    PII_STATE_KEYS,
    render_consent_withdrawal,
    render_pii_gate,
)
from data_compass.ui.relationships import ERD_STATE_KEY, render_relationships_form
from data_compass.upload.ingest import (
    MAX_FILES,
    ParsedFile,
    parse_file,
    validate_file_count,
    validate_file_extension,
)

UPLOAD_STATE_KEY = "uploaded_files"
_VALIDATION_KEY = "erd_validation"


def _all_upload_state_keys() -> tuple[str, ...]:
    """Every session key that holds uploaded-dataset state."""
    from data_compass.ui.query import _UPLOAD_CONN_KEY

    return (
        UPLOAD_STATE_KEY, ERD_STATE_KEY, _VALIDATION_KEY, "erd_signed_off",
        "_pending_fks", "_plausibility_suggestions", "_plausibility_accepted",
        _UPLOAD_CONN_KEY, *PII_STATE_KEYS,
    )


def clear_uploaded_datasets(session) -> bool:
    """Remove all uploaded-dataset state from the session, returning whether
    anything was present.

    Idempotent — safe to call when nothing is loaded. Used to drop a recruiter's
    in-memory uploads when their login ends, whether by an explicit logout or by
    token expiry/quota exhaustion.
    """
    keys = _all_upload_state_keys()
    removed = any(k in session for k in keys)
    for key in keys:
        session.pop(key, None)
    return removed


def render_upload_panel() -> None:
    """Render the Upload panel in the main content area."""
    st.header(t("upload.header"))

    if not key_router.is_logged_in(st.session_state):
        st.warning(t("upload.anon_warning"))
        return

    # ------------------------------------------------------------------
    # Terms of Use gate (Step 8.5): no upload until the ToS are accepted.
    # ------------------------------------------------------------------
    if not render_tos_gate():
        return

    # ------------------------------------------------------------------
    # File uploader
    # ------------------------------------------------------------------
    uploaded = st.file_uploader(
        label=t("upload.file_label"),
        type=["csv", "xlsx"],
        accept_multiple_files=True,
        key="file_uploader",
    )

    if uploaded:
        # New files chosen — validate, parse, reset ERD state
        count_error = validate_file_count(uploaded)
        if count_error:
            st.error(t(count_error))
            return

        parsed: list[ParsedFile] = []
        for f in uploaded:
            if not validate_file_extension(f.name):
                st.error(t("upload.unsupported_format").format(name=f.name))
                continue
            try:
                df = parse_file(f.name, f.read())
                parsed.append(ParsedFile(name=f.name, df=df))
            except Exception as exc:
                st.error(t("upload.parse_error").format(name=f.name, error=str(exc)))

        if parsed:
            # Overwrite stored files and clear all downstream ERD/PII state
            st.session_state[UPLOAD_STATE_KEY] = parsed
            for key in _all_upload_state_keys():
                if key != UPLOAD_STATE_KEY:
                    st.session_state.pop(key, None)
            st.success(t("upload.success").format(count=len(parsed)))

    # ------------------------------------------------------------------
    # Use stored files (remain after navigation away and back)
    # ------------------------------------------------------------------
    stored: list[ParsedFile] = st.session_state.get(UPLOAD_STATE_KEY, [])
    if not stored:
        return

    # ------------------------------------------------------------------
    # PII failsafe (Step 8.2): block-and-warn → mask before any downstream
    # work. Nothing below runs until the data is clean or masked, so raw
    # personal data never reaches a preview, a prompt or the cache.
    # ------------------------------------------------------------------
    if not render_pii_gate(stored):
        return
    # Re-read in case masking replaced the stored files with masked copies.
    stored = st.session_state.get(UPLOAD_STATE_KEY, [])

    # Town/Postcode consent withdrawal control (Step 8.4 "forget" path).
    render_consent_withdrawal()

    # Build table schemas from stored DataFrames
    tables: list[TableSchema] = [
        infer_schema(table_name_from_filename(pf.name), pf.df)
        for pf in stored
    ]

    # File previews
    st.subheader(t("upload.uploaded_header"))
    for pf in stored:
        rows, cols = pf.df.shape
        with st.expander(pf.name):
            st.caption(t("upload.rows_cols").format(rows=rows, cols=cols))
            st.dataframe(pf.df.head(5), use_container_width=True)

    # PK/FK declaration form (always visible while files are loaded)
    render_relationships_form(tables)

    # ------------------------------------------------------------------
    # After declaration confirmed: run validation + show sign-off
    # ------------------------------------------------------------------
    declaration = st.session_state.get(ERD_STATE_KEY)
    if declaration is None:
        return

    # Run deterministic validation once and cache the result
    if _VALIDATION_KEY not in st.session_state:
        dfs = {table_name_from_filename(pf.name): pf.df for pf in stored}
        st.session_state[_VALIDATION_KEY] = validate_erd(declaration, dfs)

    render_erd_signoff(declaration, st.session_state[_VALIDATION_KEY])
