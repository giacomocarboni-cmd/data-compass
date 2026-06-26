"""About / How this was made page."""

import streamlit as st

from data_compass.i18n import t
from data_compass.ui.legal import render_privacy_notice

_STACK_KEYS = [
    "stack_streamlit",
    "stack_duckdb",
    "stack_claude",
    "stack_faiss",
    "stack_pandas",
    "stack_plotly",
    "stack_argon2",
    "stack_python",
]


def render() -> None:
    """Render the About / How this was made page."""
    st.title(t("about.header"))
    st.caption(t("about.portfolio_caption"))
    st.divider()

    st.subheader(t("about.built_header"))
    st.markdown(t("about.clean_room_note"))
    st.markdown(t("about.dev_skill_note"))

    st.subheader(t("about.stack_header"))
    items = "\n".join(f"- {t(f'about.{k}')}" for k in _STACK_KEYS)
    st.markdown(items)

    st.divider()
    st.subheader(t("about.links_header"))
    repo_url = t("about.repo_url")
    st.markdown(f"- [{t('about.repo_link_text')}]({repo_url})")

    with st.expander(t("about.privacy_link_text")):
        render_privacy_notice()
