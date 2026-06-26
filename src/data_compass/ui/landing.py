"""Landing page component — rendered when no dataset is selected."""

import base64
import html
from pathlib import Path

import streamlit as st

from data_compass.i18n import t

_ASSETS = Path(__file__).parent.parent / "assets"


def _hero_data_uri() -> str:
    """Return the hero image as a base64 data URI.

    Prefers hero.png (AI-generated nautical chart) over the hero.svg fallback.
    """
    for name in ("hero.png", "hero.svg"):
        path = _ASSETS / name
        if path.exists():
            mime = "image/png" if path.suffix == ".png" else "image/svg+xml"
            data = base64.b64encode(path.read_bytes()).decode()
            return f"data:{mime};base64,{data}"
    return ""


# Title + tagline overlaid on the left of the hero chart, behind a soft
# parchment scrim (matching the chart's paper) so the navy text stays legible.
_HERO_CSS = """
<style>
.dc-hero { position: relative; width: 100%; margin-bottom: 0.75rem; }
.dc-hero img { width: 100%; display: block; border-radius: 8px; }
.dc-hero-text {
    position: absolute; inset: 0; width: 58%;
    display: flex; flex-direction: column; justify-content: center;
    padding: 0 clamp(1rem, 4%, 3rem);
    border-radius: 8px 0 0 8px;
    background: linear-gradient(90deg,
        rgba(242,228,207,0.92) 0%,
        rgba(242,228,207,0.78) 55%,
        rgba(242,228,207,0) 100%);
}
.dc-hero-text h1 {
    margin: 0 0 0.4rem 0; line-height: 1.1; font-weight: 600; color: #122F4F;
    font-size: clamp(1.5rem, 3.4vw, 2.6rem);
}
.dc-hero-text p {
    margin: 0; font-style: italic; color: #304860;
    font-size: clamp(0.8rem, 1.5vw, 1.05rem);
}
/* On phones the chart is short — drop the scrim full-width for legibility. */
@media (max-width: 640px) {
    .dc-hero-text { width: 100%; border-radius: 8px;
        background: linear-gradient(90deg,
            rgba(242,228,207,0.90) 0%, rgba(242,228,207,0.78) 100%); }
}
</style>
"""


def _hero_html() -> str:
    """Return the hero <img> with title/tagline overlaid, or '' if no asset."""
    uri = _hero_data_uri()
    if not uri:
        return ""
    title = html.escape(t("app.title"))
    tagline = html.escape(t("app.tagline"))
    return (
        f'<div class="dc-hero">'
        f'<img src="{uri}" alt="Data Compass — nautical chart banner">'
        f'<div class="dc-hero-text"><h1>{title}</h1><p>{tagline}</p></div>'
        f"</div>"
    )


def render() -> None:
    """Render the Data Compass landing view."""
    hero = _hero_html()
    if hero:
        st.markdown(_HERO_CSS + hero, unsafe_allow_html=True)
    else:
        # No banner asset — fall back to a plain heading + tagline.
        st.title(t("app.title"))
        st.markdown(f"*{t('app.tagline')}*")

    st.markdown(t("app.subtitle"))
    st.divider()
    st.info(t("landing.choose_dataset"))
