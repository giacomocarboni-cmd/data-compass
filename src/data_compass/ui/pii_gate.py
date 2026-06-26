"""
PII block-and-warn gate — Phase 8, Step 8.2.

Sits in the upload journey between parsing files and any downstream work that
could send data to a prompt or the cache (schema inference, ERD sign-off,
querying). When the deterministic scan (Step 8.1) flags personal data the gate
*stops* the journey, reports what was found, and offers two choices:

  * **Mask and continue** — masks the flagged columns in place (Step 8.2's
    one-way pseudonymiser), replaces the stored files with the masked copies,
    and discards the raw ones. Only then does the journey continue.
  * **Cancel upload** — discards the uploaded files and all derived state.

Nothing downstream runs until the gate returns True, so raw PII never reaches
a prompt or the cache.

Public API
----------
PII_STATE_KEYS   tuple of session keys this gate owns (cleared on new upload)
render_pii_gate(stored) -> bool
    True when it is safe to proceed (clean, or masking applied); False while
    the upload is blocked awaiting the user's decision.
"""
from __future__ import annotations

import streamlit as st

from data_compass.auth import key_router
from data_compass.auth import resource as auth_resource
from data_compass.erd.infer import table_name_from_filename
from data_compass.gdpr import audit, consent
from data_compass.i18n import t
from data_compass.pii.mask import mask_dataframe, new_salt
from data_compass.pii.scan import scan_dataframe
from data_compass.upload.ingest import ParsedFile

_RESULTS_KEY = "pii_scan_results"
_RESOLVED_KEY = "pii_resolved"
_MASKED_SUMMARY_KEY = "pii_masked_summary"
_RETAIN_POSTCODE_KEY = "_pii_retain_postcode"

# The deterministic type that the Town/Postcode consent (Step 8.4) covers.
_POSTCODE_TYPE = "uk_postcode"

# Session keys owned by the gate; the upload panel clears these on a new upload.
PII_STATE_KEYS: tuple[str, ...] = (
    _RESULTS_KEY, _RESOLVED_KEY, _MASKED_SUMMARY_KEY, _RETAIN_POSTCODE_KEY,
)


def _subject() -> str:
    """Per-user consent/audit identity for the current session."""
    return key_router.get_upload_scope(st.session_state)


def _scan_stored(stored: list[ParsedFile]) -> dict:
    """Scan each stored file, keyed by file name."""
    return {
        pf.name: scan_dataframe(table_name_from_filename(pf.name), pf.df)
        for pf in stored
    }


def _on_mask(stored: list[ParsedFile]) -> None:
    """Mask flagged columns (honouring Town/Postcode consent), log, replace.

    If the user opted to retain Town/Postcode, postcode columns are kept (and a
    consent record is written); everything else is masked. Each file's
    detection and its resolution are written to the audit log. The raw
    DataFrames are discarded by replacing the stored files with masked copies.
    """
    salt = new_salt()
    results = st.session_state.get(_RESULTS_KEY, {})
    retain_postcode = bool(st.session_state.get(_RETAIN_POSTCODE_KEY, False))
    subject = _subject()
    auth_conn = auth_resource.get_auth_conn()

    if retain_postcode:
        consent.grant_consent(auth_conn, subject)

    masked: list[ParsedFile] = []
    masked_columns = 0
    for pf in stored:
        result = results.get(pf.name)
        findings = result.findings if result is not None else []
        if not findings:
            masked.append(pf)
            continue

        if retain_postcode:
            to_mask = [f for f in findings if f.pii_type != _POSTCODE_TYPE]
            retained = [f for f in findings if f.pii_type == _POSTCODE_TYPE]
        else:
            to_mask, retained = findings, []

        masked_df = mask_dataframe(pf.df, to_mask, salt=salt) if to_mask else pf.df
        masked.append(ParsedFile(pf.name, masked_df))
        masked_columns += len(to_mask)

        table = table_name_from_filename(pf.name)
        if to_mask:
            audit.log_detection(auth_conn, subject, table, to_mask, audit.RESOLUTION_MASKED)
        if retained:
            audit.log_detection(
                auth_conn, subject, table, retained, audit.RESOLUTION_RETAINED
            )

    # Replace stored files with masked copies; the raw DataFrames are dropped.
    st.session_state["uploaded_files"] = masked
    st.session_state[_MASKED_SUMMARY_KEY] = masked_columns
    st.session_state[_RESOLVED_KEY] = True
    # Cached scan results refer to the now-discarded raw data.
    st.session_state.pop(_RESULTS_KEY, None)


def _on_cancel() -> None:
    """Discard the uploaded files and all derived upload/ERD/PII state."""
    from data_compass.ui.query import _UPLOAD_CONN_KEY
    from data_compass.ui.relationships import ERD_STATE_KEY

    # Record the cancellation in the audit trail before clearing state.
    results = st.session_state.get(_RESULTS_KEY, {})
    subject = _subject()
    auth_conn = auth_resource.get_auth_conn()
    for name, result in results.items():
        if result.has_pii:
            audit.log_detection(
                auth_conn, subject, table_name_from_filename(name),
                result.findings, audit.RESOLUTION_CANCELLED,
            )

    for key in (
        "uploaded_files",
        ERD_STATE_KEY,
        "erd_validation",
        "erd_signed_off",
        "_pending_fks",
        "_plausibility_suggestions",
        "_plausibility_accepted",
        _UPLOAD_CONN_KEY,
        *PII_STATE_KEYS,
    ):
        st.session_state.pop(key, None)


def _on_withdraw() -> None:
    """Withdraw Town/Postcode consent: re-mask, drop derived cache, log."""
    subject = _subject()
    auth_conn = auth_resource.get_auth_conn()
    consent.withdraw_consent(auth_conn, subject)

    salt = new_salt()
    stored = st.session_state.get("uploaded_files", [])
    remasked: list[ParsedFile] = []
    for pf in stored:
        table = table_name_from_filename(pf.name)
        scan = scan_dataframe(table, pf.df)
        postcode = [f for f in scan.findings if f.pii_type == _POSTCODE_TYPE]
        if postcode:
            remasked.append(ParsedFile(pf.name, mask_dataframe(pf.df, postcode, salt=salt)))
            audit.log_detection(
                auth_conn, subject, table, postcode, audit.RESOLUTION_MASKED,
                detail="re-masked on consent withdrawal",
            )
        else:
            remasked.append(pf)
    st.session_state["uploaded_files"] = remasked

    # Drop the uploaded DuckDB connection and any derived cached results.
    from data_compass.cache import resource as cache_resource
    from data_compass.cache import store as cache_store
    from data_compass.ui.query import _UPLOAD_CONN_KEY

    st.session_state.pop(_UPLOAD_CONN_KEY, None)
    try:
        cache_store.delete_templates_for_scope(
            cache_resource.get_cache_conn(), "uploaded", subject
        )
    except Exception:
        pass  # cache drop is best-effort; consent record + re-mask are the guarantee
    st.session_state["_pii_withdrawn"] = True


def render_consent_withdrawal() -> None:
    """If Town/Postcode consent is active, offer to withdraw it (the 'forget' path)."""
    if not key_router.is_logged_in(st.session_state):
        return
    auth_conn = auth_resource.get_auth_conn()
    subject = _subject()
    if st.session_state.pop("_pii_withdrawn", False):
        st.success(t("pii.withdrawn_notice"))
    if consent.has_consent(auth_conn, subject):
        st.caption(t("pii.consent_active"))
        st.button(t("pii.withdraw_button"), on_click=_on_withdraw, key="pii_withdraw_button")


def render_pii_gate(stored: list[ParsedFile]) -> bool:
    """Render the PII gate. Return True if it is safe to proceed."""
    if st.session_state.get(_RESOLVED_KEY):
        masked_columns = st.session_state.get(_MASKED_SUMMARY_KEY, 0)
        if masked_columns:
            st.info(t("pii.masked_notice").format(count=masked_columns))
        return True

    if _RESULTS_KEY not in st.session_state:
        st.session_state[_RESULTS_KEY] = _scan_stored(stored)
    results = st.session_state[_RESULTS_KEY]

    flagged = {name: r for name, r in results.items() if r.has_pii}
    if not flagged:
        st.session_state[_RESOLVED_KEY] = True
        return True

    # Block and report.
    st.error(t("pii.blocked_header"))
    st.warning(t("pii.blocked_body"))
    for name, result in flagged.items():
        with st.expander(t("pii.file_findings").format(name=name)):
            for finding in result.findings:
                st.write(
                    t("pii.finding_row").format(
                        column=finding.column,
                        type=t(f"pii.type.{finding.pii_type}"),
                        count=finding.match_count,
                    )
                )

    # Town/Postcode consent prompt (Step 8.4) — only when a postcode was found.
    has_postcode = any(
        f.pii_type == _POSTCODE_TYPE
        for r in flagged.values()
        for f in r.findings
    )
    if has_postcode:
        st.checkbox(t("pii.retain_postcode"), key=_RETAIN_POSTCODE_KEY)

    col_mask, col_cancel = st.columns(2)
    col_mask.button(
        t("pii.mask_button"),
        on_click=_on_mask,
        args=(stored,),
        type="primary",
        key="pii_mask_button",
    )
    col_cancel.button(
        t("pii.cancel_button"),
        on_click=_on_cancel,
        key="pii_cancel_button",
    )
    st.caption(t("pii.mask_caption"))
    return False
