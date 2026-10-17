"""
Command-line admin password reset (for when you have shell access).

    python -m data_compass.auth.reset_admin

Prompts for the new password, then creates or updates the admin account in the
auth database. On hosts with no shell (e.g. Streamlit Community Cloud) set the
``ADMIN_PASSWORD_RESET`` secret instead.
"""
from __future__ import annotations

import getpass
import sys

from data_compass.auth import store
from data_compass.config import ADMIN_USERNAME, AUTH_DB_PATH


def main() -> int:
    print(f"Resetting the password for '{ADMIN_USERNAME}' in {AUTH_DB_PATH}")
    new = getpass.getpass("New password: ")
    if new != getpass.getpass("Repeat: "):
        print("The passwords do not match.", file=sys.stderr)
        return 1
    conn = store.connect(AUTH_DB_PATH)
    try:
        result = store.reset_admin_password(conn, ADMIN_USERNAME, new)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Done ({result}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
