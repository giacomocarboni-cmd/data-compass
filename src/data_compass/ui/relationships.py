"""
PK/FK declaration form — Phase 7, Step 7.2.

render_relationships_form(tables) renders the schema declaration step:
  * A PK selectbox per table (pre-filled with the most-unique column).
  * A FK builder: four selectboxes (from table/col → to table/col) + "Add".
  * A list of declared FKs with individual "Remove" buttons.
  * A "Confirm schema" button that writes an ERDDeclaration to
    session_state["erd_declaration"].

Session-state keys used:
  _pk_{table}               — chosen PK column for each table
  _fk_from_table / _col     — FK builder dropdown selections
  _fk_to_table / _col
  _pending_fks              — list[dict] of {"from_table", "from_col",
                                              "to_table", "to_col"}
"""
from __future__ import annotations

import streamlit as st

from data_compass.erd.infer import ERDDeclaration, Relationship, TableSchema
from data_compass.i18n import t

ERD_STATE_KEY = "erd_declaration"
_PENDING_FKS = "_pending_fks"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_relationships_form(tables: list[TableSchema]) -> None:
    """Render the PK/FK declaration form for the given list of table schemas."""
    if not tables:
        return

    st.divider()
    st.subheader(t("relationships.header"))
    st.caption(t("relationships.caption"))

    _render_pk_section(tables)
    st.divider()
    _render_fk_section(tables)
    st.divider()

    if st.button(t("relationships.confirm_button"), type="primary", key="confirm_schema_btn"):
        _store_declaration(tables)


# ---------------------------------------------------------------------------
# PK section
# ---------------------------------------------------------------------------

def _render_pk_section(tables: list[TableSchema]) -> None:
    st.markdown(f"**{t('relationships.pk_header')}**")
    st.caption(t("relationships.pk_caption"))
    for tbl in tables:
        col_names = [c.name for c in tbl.columns]
        default_pk = _suggest_pk(tbl)
        default_idx = col_names.index(default_pk) if default_pk in col_names else 0
        st.selectbox(
            label=t("relationships.pk_label").format(table=tbl.name),
            options=col_names,
            index=default_idx,
            key=f"_pk_{tbl.name}",
        )


def _suggest_pk(tbl: TableSchema) -> str:
    """Return the column name with the highest unique_ratio as PK suggestion."""
    if not tbl.columns:
        return ""
    return max(tbl.columns, key=lambda c: c.unique_ratio).name


# ---------------------------------------------------------------------------
# FK section
# ---------------------------------------------------------------------------

def _render_fk_section(tables: list[TableSchema]) -> None:
    st.markdown(f"**{t('relationships.fk_header')}**")
    st.caption(t("relationships.fk_caption"))

    if len(tables) < 2:
        st.info(t("relationships.fk_need_two"))
        return

    table_names = [tbl.name for tbl in tables]
    col_map = {tbl.name: [c.name for c in tbl.columns] for tbl in tables}

    # FK builder row
    cols = st.columns([2, 2, 2, 2, 1])
    from_table = cols[0].selectbox(
        t("relationships.fk_from_table"), table_names, key="_fk_from_table"
    )
    from_col = cols[1].selectbox(
        t("relationships.fk_from_col"), col_map.get(from_table, []), key="_fk_from_col"
    )
    to_table = cols[2].selectbox(
        t("relationships.fk_to_table"), table_names, key="_fk_to_table"
    )
    to_col = cols[3].selectbox(
        t("relationships.fk_to_col"), col_map.get(to_table, []), key="_fk_to_col"
    )
    cols[4].markdown("&nbsp;", unsafe_allow_html=True)  # vertical spacing
    cols[4].button(
        t("relationships.fk_add_button"),
        key="fk_add_btn",
        on_click=_cb_add_fk,
        args=(from_table, from_col, to_table, to_col),
    )

    # List of declared FKs
    pending: list[dict] = st.session_state.get(_PENDING_FKS, [])
    if pending:
        st.markdown(f"*{t('relationships.fk_declared')}*")
        for i, fk in enumerate(pending):
            c1, c2 = st.columns([5, 1])
            c1.markdown(
                f"`{fk['from_table']}.{fk['from_col']}` → "
                f"`{fk['to_table']}.{fk['to_col']}`"
            )
            c2.button(
                t("relationships.fk_remove_button"),
                key=f"fk_remove_{i}",
                on_click=_cb_remove_fk,
                args=(i,),
            )


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def _cb_add_fk(from_table, from_col, to_table, to_col) -> None:
    if from_table == to_table and from_col == to_col:
        return  # self-referencing FK is meaningless; silently ignore
    pending: list[dict] = st.session_state.setdefault(_PENDING_FKS, [])
    new_fk = {
        "from_table": from_table,
        "from_col": from_col,
        "to_table": to_table,
        "to_col": to_col,
    }
    if new_fk not in pending:
        pending.append(new_fk)


def _cb_remove_fk(index: int) -> None:
    pending: list[dict] = st.session_state.get(_PENDING_FKS, [])
    if 0 <= index < len(pending):
        pending.pop(index)


def _store_declaration(tables: list[TableSchema]) -> None:
    """Build and store the ERDDeclaration from current widget state."""
    primary_keys: dict[str, str] = {}
    for tbl in tables:
        pk_col = st.session_state.get(f"_pk_{tbl.name}")
        if pk_col:
            primary_keys[tbl.name] = pk_col

    relationships = [
        Relationship(
            from_table=fk["from_table"],
            from_col=fk["from_col"],
            to_table=fk["to_table"],
            to_col=fk["to_col"],
        )
        for fk in st.session_state.get(_PENDING_FKS, [])
    ]

    st.session_state[ERD_STATE_KEY] = ERDDeclaration(
        tables=tables,
        primary_keys=primary_keys,
        relationships=relationships,
    )
