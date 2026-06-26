"""Data Compass — Streamlit entry point."""

from pathlib import Path

import streamlit as st

from data_compass.auth import key_router
from data_compass.i18n import t
from data_compass.ui import styles
from data_compass.ui.landing import render as render_landing
from data_compass.ui.dataset_browser import render_sidebar_picker, render_browser
from data_compass.ui.query import render_api_key_sidebar, render_query_panel
from data_compass.ui.auth import render_account_panel, purge_expired_recruiter_uploads
from data_compass.ui.upload import render_upload_panel
from data_compass.ui.about import render as render_about
from data_compass.ui.how_it_works import render as render_how_it_works

_ASSETS = Path(__file__).parent / "src" / "data_compass" / "assets"

st.set_page_config(
    page_title=t("app.title"),
    page_icon="🧭",
    layout="wide",
)

styles.inject()

st.logo(
    str(_ASSETS / "logo.svg"),
    icon_image=str(_ASSETS / "logo_icon.svg"),
)

# Once a recruiter token has expired or hit its query cap, remove the datasets
# they uploaded this session. The login itself stays intact so the query gate
# can still explain why queries are blocked.
purge_expired_recruiter_uploads(st.session_state)


def _go_home() -> None:
    """Return to the hero landing: select Datasets and clear any chosen dataset."""
    st.session_state["nav_selection"] = t("app.nav.datasets")
    st.session_state["_dataset_picker"] = t("dataset_browser.select_placeholder")
    st.session_state["selected_dataset_id"] = None


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.button(
        t("app.home_button"),
        key="home_btn",
        icon=":material/home:",
        use_container_width=True,
        on_click=_go_home,
    )
    st.divider()

    nav = st.radio(
        label="nav",
        options=[
            t("app.nav.datasets"),
            t("app.nav.query"),
            t("app.nav.upload"),
            t("app.nav.account"),
            t("app.nav.about"),
            t("app.nav.how_it_works"),
        ],
        label_visibility="collapsed",
        key="nav_selection",
    )

    st.divider()
    selected_dataset = render_sidebar_picker()

    # Public tier brings its own key; logged-in tiers use the owner key, so the
    # BYOK input is hidden once authenticated.
    if not key_router.is_logged_in(st.session_state):
        st.divider()
        render_api_key_sidebar()

# ---------------------------------------------------------------------------
# Main content — route by nav selection
# ---------------------------------------------------------------------------
if nav == t("app.nav.datasets"):
    if selected_dataset:
        render_browser(selected_dataset)
    else:
        render_landing()
elif nav == t("app.nav.query"):
    render_query_panel(selected_dataset)
elif nav == t("app.nav.upload"):
    render_upload_panel()
elif nav == t("app.nav.account"):
    render_account_panel()
elif nav == t("app.nav.about"):
    render_about()
else:
    render_how_it_works()
