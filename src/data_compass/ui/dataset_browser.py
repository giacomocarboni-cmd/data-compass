"""
Dataset picker and table browser component.

Renders a dataset selector in the sidebar and, once a dataset is chosen,
displays its tables with schema info and a row preview in the main panel.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from data_compass.i18n import t

# Ensure data/ registry is importable from the project root
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from data.registry import REGISTRY, get_dataset  # noqa: E402
from data_compass.data.loader import load_dataset, get_schema  # noqa: E402


# ---------------------------------------------------------------------------
# Cached loader — one DuckDB connection per dataset per process lifetime
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _cached_load(dataset_id: str):
    return load_dataset(dataset_id)


# ---------------------------------------------------------------------------
# Sidebar widget — returns the selected dataset id or None
# ---------------------------------------------------------------------------

def render_sidebar_picker() -> str | None:
    """
    Render the dataset selectbox in the sidebar.
    Returns the selected dataset id, or None if none is chosen.
    """
    options = [entry["id"] for entry in REGISTRY]
    labels  = {entry["id"]: entry["name"] for entry in REGISTRY}

    current = st.session_state.get("selected_dataset_id")
    try:
        index = options.index(current) + 1  # +1 for the placeholder
    except ValueError:
        index = 0

    # Build display list with a blank placeholder at position 0
    display = [t("dataset_browser.select_placeholder")] + [labels[o] for o in options]

    choice = st.selectbox(
        label=t("dataset_browser.select_label"),
        options=display,
        index=index,
        key="_dataset_picker",
        label_visibility="visible",
    )

    if choice == t("dataset_browser.select_placeholder"):
        st.session_state["selected_dataset_id"] = None
        return None

    selected_id = options[display.index(choice) - 1]
    st.session_state["selected_dataset_id"] = selected_id
    return selected_id


# ---------------------------------------------------------------------------
# Main panel — table browser
# ---------------------------------------------------------------------------

def render_browser(dataset_id: str) -> None:
    """Render the table browser for the given dataset in the main panel."""
    entry  = get_dataset(dataset_id)
    conn   = _cached_load(dataset_id)
    schema = get_schema(conn)

    st.header(entry["name"])
    st.markdown(entry["description"])

    # Relationships summary
    fks = entry["schema_hints"].get("foreign_keys", [])
    if fks:
        st.subheader(t("dataset_browser.relationships_header"))
        for fk in fks:
            label = t("dataset_browser.fk_arrow").format(
                from_table=fk["from_table"], from_col=fk["from_column"],
                to_table=fk["to_table"],   to_col=fk["to_column"],
            )
            st.markdown(f"- `{label}`")

    st.divider()
    st.subheader(t("dataset_browser.tables_header"))

    for table_name, cols in schema.items():
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]  # noqa: S608
        with st.expander(f"**{table_name}** — {row_count:,} {t('dataset_browser.rows_suffix')}", expanded=True):
            # Schema
            st.caption(t("dataset_browser.schema_subheader"))
            schema_df = pd.DataFrame(
                [{"Column": c.name, "Type": c.dtype} for c in cols]
            )
            st.dataframe(schema_df, width="stretch", hide_index=True)

            # Preview
            st.caption(t("dataset_browser.preview_subheader"))
            preview_df = conn.execute(f"SELECT * FROM {table_name} LIMIT 5").df()  # noqa: S608
            st.dataframe(preview_df, width="stretch", hide_index=True)

    st.caption(
        t("dataset_browser.licence_caption").format(source=entry["licence"])
    )
