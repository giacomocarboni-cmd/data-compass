"""
Process-lifetime auth connection + admin seeding — Phase 6, Step 6.5.

The auth database (users + recruiter tokens) is a single SQLite file shared
across sessions. The connection is cached for the process lifetime via
``st.cache_resource``. On first creation the admin account is seeded from the
environment (``ADMIN_USERNAME`` / ``ADMIN_PASSWORD``) and the recruiter-token
table is ensured.

Tests patch ``get_auth_conn`` to inject an isolated in-memory store.
"""
from __future__ import annotations

import sqlite3

import streamlit as st

from data_compass.auth import recruiter, store
from data_compass.config import ADMIN_PASSWORD, ADMIN_USERNAME, AUTH_DB_PATH


def init_auth_db(conn: sqlite3.Connection) -> None:
    """Ensure both auth tables exist and seed the admin from the environment."""
    recruiter.ensure_schema(conn)
    # store.connect already created the users table; seed_admin is idempotent
    # and refuses a blank password, so an unset ADMIN_PASSWORD seeds nothing.
    store.seed_admin(conn, ADMIN_USERNAME, ADMIN_PASSWORD)


@st.cache_resource(show_spinner=False)
def get_auth_conn() -> sqlite3.Connection:
    """Return the shared, process-lifetime auth connection (seeded on creation)."""
    conn = store.connect(AUTH_DB_PATH)
    init_auth_db(conn)
    return conn
