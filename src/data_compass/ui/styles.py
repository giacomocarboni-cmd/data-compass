"""Inject CSS and web-font overrides for the nautical theme."""

import streamlit as st

_FONT_LINK = (
    "<link rel='preconnect' href='https://fonts.googleapis.com'>"
    "<link href='https://fonts.googleapis.com/css2?family=IBM+Plex+Sans"
    ":ital,wght@0,300;0,400;0,600;0,700;1,400&display=swap' rel='stylesheet'>"
)

_CSS = """
<style>
/* Apply IBM Plex Sans across the whole app. */
.stApp, .stApp * {
    font-family: 'IBM Plex Sans', 'Segoe UI', Arial, sans-serif;
}
/* ...but never override Streamlit's Material Symbols icon font, or icon
   ligatures (e.g. the sidebar-collapse arrow) render as raw text. */
span[data-testid="stIconMaterial"],
.material-symbols-rounded,
.material-symbols-outlined {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined' !important;
}
/* Tighten the default top padding. */
.block-container {
    padding-top: 1.25rem !important;
    max-width: 1120px;
}
/* Headings: medium weight feels cleaner than the Streamlit default bold. */
h1 { font-weight: 600 !important; }
h2 { font-weight: 600 !important; }
h3 { font-weight: 500 !important; }
/* Subtle border-radius on info/warning boxes. */
div[data-testid="stAlert"] { border-radius: 6px; }
/* Code blocks: keep monospace but honour the theme background. */
code, pre { font-family: 'IBM Plex Mono', 'Consolas', monospace !important; }
</style>
"""


def inject() -> None:
    """Inject global CSS once per render cycle."""
    st.markdown(_FONT_LINK + _CSS, unsafe_allow_html=True)
