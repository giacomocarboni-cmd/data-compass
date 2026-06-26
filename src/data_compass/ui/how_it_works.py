"""How it works — 5-step plain-English explainer page."""

import streamlit as st

from data_compass.i18n import t

_STEPS = [
    ("step1_title", "step1_body"),
    ("step2_title", "step2_body"),
    ("step3_title", "step3_body"),
    ("step4_title", "step4_body"),
    ("step5_title", "step5_body"),
]


def render() -> None:
    """Render the How it works explainer page."""
    st.title(t("how_it_works.header"))
    st.markdown(t("how_it_works.intro"))
    st.divider()

    for title_key, body_key in _STEPS:
        st.subheader(t(f"how_it_works.{title_key}"))
        st.markdown(t(f"how_it_works.{body_key}"))

    st.divider()

    with st.expander(t("how_it_works.cache_note_header")):
        st.markdown(t("how_it_works.cache_note_body"))

    with st.expander(t("how_it_works.synthetic_note_header")):
        st.markdown(t("how_it_works.synthetic_note_body"))
