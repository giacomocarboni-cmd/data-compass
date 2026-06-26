"""Visual-QC screenshot harness for Data Compass.

Drives the Streamlit sidebar nav through every reachable page at two viewport
widths and saves full-page PNGs to qc_shots/. Throwaway tooling — not shipped.

Key trick: Streamlit holds a persistent websocket, so `networkidle` fires
immediately and screenshots land mid-rerun. We instead wait for each page's
own heading (role=heading) to be visible before shooting.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "http://localhost:8765/"
OUT = Path(__file__).parent / "qc_shots"
OUT.mkdir(exist_ok=True)

# (nav radio label, role=heading sentinel that proves the page rendered)
PAGES = [
    ("Datasets", "Data Compass"),
    ("Query", "Query your data"),
    ("Upload", "Upload your data"),
    ("Account", "Account"),
    ("About", "About Data Compass"),
    ("How it works", "How it works"),
]

VIEWPORTS = {
    "desktop": (1440, 900),
    "narrow": (768, 1000),
}

# Hide the dev toolbar (Deploy/Stop/⋮) and status widget for clean shots.
HIDE_CHROME = """
[data-testid="stToolbar"], [data-testid="stStatusWidget"],
[data-testid="stDecoration"] { display: none !important; }
"""


def open_sidebar(page):
    """If the sidebar is collapsed (narrow viewport), expand it."""
    for sel in (
        '[data-testid="stSidebarCollapsedControl"]',
        '[data-testid="collapsedControl"]',
    ):
        btn = page.locator(sel)
        if btn.count() and btn.first.is_visible():
            btn.first.click()
            page.wait_for_timeout(600)
            return


def goto_page(page, label, heading, vp_name):
    """Navigate to a page and wait for its heading to confirm the rerun landed."""
    open_sidebar(page)
    try:
        page.get_by_text(label, exact=True).first.click(timeout=6000)
    except Exception as e:
        print(f"  ! click {label!r} ({vp_name}) failed: {e}")
        return
    try:
        page.get_by_role("heading", name=heading, exact=False).first.wait_for(
            state="visible", timeout=10000
        )
    except Exception:
        print(f"  ~ heading {heading!r} not seen on {label!r} ({vp_name})")
    page.wait_for_timeout(900)  # let fonts/icons settle


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for vp_name, (w, h) in VIEWPORTS.items():
            ctx = browser.new_context(viewport={"width": w, "height": h},
                                      device_scale_factor=2)
            page = ctx.new_page()
            page.goto(URL, wait_until="domcontentloaded")
            # Wait for the very first render (landing heading) before anything.
            page.get_by_role("heading", name="Data Compass").first.wait_for(
                state="visible", timeout=30000
            )
            page.add_style_tag(content=HIDE_CHROME)
            page.wait_for_timeout(1500)

            for i, (label, heading) in enumerate(PAGES):
                goto_page(page, label, heading, vp_name)
                slug = label.lower().replace(" ", "_")
                fname = OUT / f"{vp_name}_{i}_{slug}.png"
                page.screenshot(path=str(fname), full_page=True)
                print(f"  saved {fname.name}")

            ctx.close()
        browser.close()
    print("done")


if __name__ == "__main__":
    sys.exit(main())
