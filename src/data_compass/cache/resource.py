"""
Process-lifetime cache connection — Phase 5, Step 5.6.

The cache database is a single SQLite file shared across all sessions, so a
template stored by one visitor can serve the next. The connection is cached for
the process lifetime via ``st.cache_resource``.

Tests patch ``get_cache_conn`` to inject an isolated in-memory store.
"""
from __future__ import annotations

import sqlite3

import streamlit as st

from data_compass.cache import store
from data_compass.config import CACHE_DB_PATH


@st.cache_resource(show_spinner=False)
def get_cache_conn() -> sqlite3.Connection:
    """Return the shared, process-lifetime cache connection."""
    return store.connect(CACHE_DB_PATH)
