"""Central configuration — model IDs, per-MTok rates, and tuneable parameters.

All monetary values are in USD per million tokens (MTok), matching the Anthropic
pricing page. The UI converts to GBP at display time using the FX_RATE constant.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (two levels above this file: src/data_compass/ → root)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)


def _bootstrap_streamlit_secrets() -> None:
    """Copy st.secrets into os.environ for any keys not already set.

    Allows secrets set via Streamlit Community Cloud's "Secrets" dashboard to
    reach config.py without changing the os.getenv()-based reads below.
    No-op outside a Streamlit runtime (tests, CLI, etc.).
    """
    try:
        import streamlit as st  # noqa: PLC0415

        for key, value in st.secrets.items():
            env_key = key.upper()
            if env_key not in os.environ:
                os.environ[env_key] = str(value)
    except Exception:  # noqa: BLE001
        pass


_bootstrap_streamlit_secrets()

# ---------------------------------------------------------------------------
# Model identifiers
# ---------------------------------------------------------------------------

MODEL_HAIKU = "claude-haiku-4-5"
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_OPUS = "claude-opus-4-8"

# ---------------------------------------------------------------------------
# Per-MTok pricing (USD).  Structure: {"model-id": {"input": x, "output": y}}
# Cache reads are billed at 0.1× the input rate — see CACHE_READ_MULTIPLIER.
# ---------------------------------------------------------------------------

MODEL_RATES: dict[str, dict[str, float]] = {
    MODEL_HAIKU: {"input": 1.00, "output": 5.00},
    MODEL_SONNET: {"input": 3.00, "output": 15.00},
    MODEL_OPUS: {"input": 5.00, "output": 25.00},
}

CACHE_READ_MULTIPLIER: float = 0.1  # cache-read tokens billed at 10 % of input price

# ---------------------------------------------------------------------------
# USD → GBP conversion (approximate; update periodically)
# ---------------------------------------------------------------------------

FX_USD_TO_GBP: float = float(os.getenv("FX_USD_TO_GBP", "0.79"))

# ---------------------------------------------------------------------------
# Tiered cache settings
# ---------------------------------------------------------------------------

# Minimum Haiku confidence score (0–1) for a semantic cache hit to be accepted.
# Below this, the pipeline falls through to Sonnet generation.
CACHE_THRESHOLD: float = float(os.getenv("CACHE_THRESHOLD", "0.8"))

# Number of FAISS candidate templates retrieved before Haiku adjudication.
CACHE_TOP_K: int = int(os.getenv("CACHE_TOP_K", "3"))

# Minimum cosine similarity (0–1) a FAISS candidate must reach to be worth
# adjudicating. Clearly-unrelated templates are dropped before Haiku sees them,
# saving a call and narrowing the false-match surface. Tune up for stricter
# retrieval, down (or 0.0) to send every top-K candidate to the adjudicator.
CACHE_MIN_SIMILARITY: float = float(os.getenv("CACHE_MIN_SIMILARITY", "0.35"))

# sentence-transformers model used for local embedding (zero API cost).
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# ---------------------------------------------------------------------------
# Authentication & tiers (Phase 6)
# ---------------------------------------------------------------------------

# Owner's Anthropic key — used for the admin/recruiter tiers so logged-in users
# never need their own key. Public users always bring their own (BYOK). Empty
# when unset; the key router treats an empty owner key as "unavailable".
OWNER_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "").strip()

# Admin account, seeded on first run from the environment.
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin").strip()
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "").strip()

# Admin passwords must be renewed after this many days (Step 6.2).
ADMIN_PASSWORD_MAX_AGE_DAYS: int = int(os.getenv("ADMIN_PASSWORD_MAX_AGE_DAYS", "30"))

# Recruiter temporary-login limits (Step 6.3).
RECRUITER_QUERY_CAP: int = int(os.getenv("RECRUITER_QUERY_CAP", "20"))
RECRUITER_VALIDITY_DAYS: int = int(os.getenv("RECRUITER_VALIDITY_DAYS", "30"))

# ---------------------------------------------------------------------------
# Paths (relative to project root)
# ---------------------------------------------------------------------------

DATA_DIR: Path = _PROJECT_ROOT / "data"
CACHE_DB_PATH: Path = _PROJECT_ROOT / "cache" / "cache.db"
AUTH_DB_PATH: Path = _PROJECT_ROOT / "cache" / "auth.db"
