# Data Compass

> *Navigate your data without getting lost in deep analytical waters.*

Ask questions in plain English and let Data Compass chart the route through your dataset — no SQL required.

**Live demo:** *(URL added after deploy — see [DEPLOY.md](DEPLOY.md))*

---

## What is Data Compass?

Data Compass is a natural-language analytics assistant built as a public portfolio piece. It demonstrates the combination of quantitative analysis and LLM application engineering: you type a question, it writes the SQL, runs it in-process, and returns the result table, an auto-chart, and a short summary — along with a transparent cost line showing exactly which AI models ran and what they cost.

Key engineering showcases:

- NL→SQL via Claude Sonnet 4 with prompt-cached schema context
- Four-tier semantic cache (exact match → FAISS RAG → Haiku adjudication → Sonnet generation) for deliberate LLM cost minimisation
- GDPR-aware data handling with deterministic-first PII detection and masking
- ERD onboarding with non-destructive AI sign-off
- SQL & AI execution hardening: guard blocks file/network functions; DuckDB connections sandboxed

---

## Requirements

- Python 3.11 or later
- An Anthropic API key (bring-your-own; held in session memory only — never persisted to disk)

---

## Installation

```bash
git clone https://github.com/giacomo-carboni/data-compass
cd data-compass
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -e .
```

Copy `.env.example` to `.env` and fill in the owner API key and admin password seed (only needed for the admin/recruiter tiers — public visitors bring their own key):

```bash
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY and ADMIN_PASSWORD
```

---

## Quick Start

```bash
streamlit run app.py
```

The app opens in your browser. Select a demo dataset from the sidebar, paste your Anthropic API key, and ask a question.

---

## Features

| Feature | Status |
|---|---|
| Nautical visual identity — theme, SVG logo, hero banner | ✅ Phase 9 |
| "About / How this was made" and "How it works" pages | ✅ Phase 9 |
| PII failsafe + GDPR surfaces (ToS gate, consent, audit log) | ✅ Phase 8 |
| SQL & AI execution hardening (guard + DuckDB sandbox) | ✅ Phase 8 |
| File upload + ERD onboarding (PK/FK + AI plausibility) | ✅ Phase 7 |
| Admin + recruiter authentication + quota enforcement | ✅ Phase 6 |
| Four-tier semantic cache | ✅ Phase 5 |
| Auto-chart + NL summary + per-query cost line | ✅ Phase 4 |
| NL→SQL query engine (BYOK) | ✅ Phase 3 |
| Demo dataset browser (UK Property Sales + UK Weather Stations) | ✅ Phase 2 |
| Landing page with localised UI, locale scaffold | ✅ Phase 1 |

---

## Usage Guide

**Demo datasets.** Two datasets are bundled:

- **UK Property Sales 2024** — HM Land Registry Price Paid Data (OGL v3); tables: `transactions`, `properties`
- **UK Weather Stations 1990–2026** — Met Office Historic Station Data (OGL v3); tables: `stations`, `observations`

See `docs/DATA_LICENCES.md` for full attribution and schema details. Launch `streamlit run app.py`, select a dataset from the sidebar, and the tables load into an in-process DuckDB with a 5-row preview.

**Querying.** Choose a dataset, paste your Anthropic API key in the sidebar, switch to the **Query** tab and ask a question in plain English. Data Compass returns the generated read-only SQL, the result table, an auto-chart, a one-paragraph summary, and a cost line. Repeat or near-identical questions are served from the cache at reduced or zero cost.

**Accounts & tiers.** The **Account** tab supports two logged-in tiers in addition to the public (BYOK) experience:

- **Public** — anyone; brings their own Anthropic API key (held in session memory only).
- **Recruiter** — logs in with a one-off access token; queries use the *owner's* key, capped at 20 queries within 30 days (configurable). Remaining quota is shown on the Query tab; once the cap or expiry is reached, further queries are blocked with a clear message.
- **Admin** — username + password (seeded from the environment on first run); uses the owner's key. Admin passwords are flagged for renewal after 30 days.

Logged-in tiers do not need to enter an API key — the owner's key is used and never exposed to public visitors.

**Upload & ERD onboarding.** Logged-in users can navigate to the **Upload** tab and upload up to 3 CSV or XLSX files. After uploading:

1. Accept the **Terms of Use** (warranty that no real personal data is present; **Privacy Notice** reachable from the same screen).
2. A deterministic, local **PII scan** checks every column for emails, UK postcodes, phone numbers, NINOs, payment cards, and dates of birth. Detected personal data must be **masked** (irreversible — replaced with letters-only pseudonyms) before the upload proceeds. Raw values are never stored, cached, or sent to the AI.
3. Data Compass infers column types and presents a form to declare primary keys and foreign-key relationships.
4. Three deterministic checks run (PK uniqueness, FK type compatibility, FK orphan rate) and surface issues as warnings.
5. An optional **AI plausibility check** (Haiku) reviews the declared joins for semantic sense; each suggestion can be accepted or dismissed.
6. Clicking **Sign off ERD** finalises the schema. The **Query** tab then shows a *Query your uploaded data* toggle for cross-table JOIN queries.

Uploaded data is isolated per login session and never shared with the public cache.

**Privacy & caching.** A caching warning is shown to all users on the Query tab. Questions, generated SQL, and short result summaries may be cached and reused across sessions. Do not enter confidential information. See [PRIVACY_NOTICE.md](PRIVACY_NOTICE.md) *(DRAFT — to be reviewed before public deployment)*.

---

## Configuration

All configuration lives in `src/data_compass/config.py` and can be overridden via environment variables:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Owner key (admin/recruiter tier only) |
| `ADMIN_PASSWORD` | — | Admin seed; blank = no admin seeded; change after first login |
| `ADMIN_USERNAME` | `admin` | Admin login name |
| `ADMIN_PASSWORD_MAX_AGE_DAYS` | `30` | Admin password renewal age |
| `RECRUITER_QUERY_CAP` | `20` | Max queries per recruiter token |
| `RECRUITER_VALIDITY_DAYS` | `30` | Recruiter token lifetime |
| `CACHE_THRESHOLD` | `0.8` | Minimum Haiku confidence for a semantic cache hit |
| `CACHE_TOP_K` | `3` | FAISS candidates retrieved before Haiku adjudication |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Local sentence-transformers model |
| `FX_USD_TO_GBP` | `0.79` | USD → GBP conversion rate for cost display |

For Streamlit Community Cloud deployment, set these via `st.secrets` rather than environment variables — see `docs/DEPLOY.md`.

---

## Localisation

All user-facing strings are externalised to `locales/en-GB.json`. The `t(key)` helper in `src/data_compass/i18n.py` resolves dot-separated keys (e.g. `t("app.title")` → `"Data Compass"`). Missing keys return `[missing: <key>]` rather than crashing. Additional locale files can be added by creating `locales/<tag>.json` and passing the tag to `t()`.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'data_compass'`** — run `pip install -e .` from the project root (with the venv active).

**`[missing: some.key]` in the UI** — a locale key is referenced in code but absent from `locales/en-GB.json`. Add the key to the JSON file.

**`ANTHROPIC_API_KEY not set` error on logged-in query** — set `ANTHROPIC_API_KEY` in your `.env` file (or `st.secrets` for Streamlit Cloud). Public visitors are unaffected.

**Hero image not showing** — ensure `src/data_compass/assets/hero.svg` (built-in fallback) or `hero.png` (AI-generated replacement) exists. Run the test suite to confirm: `.venv/Scripts/python -m pytest tests/test_step_9_0.py`.

**Tests time out on first run** — the first AppTest cold-start loads sentence-transformers and FAISS, which takes 10–20 s on a fresh machine. The default timeout is 30 s; subsequent runs are faster once the model is cached.

---

## For developers & maintainers

See **[CHARTROOM.md](CHARTROOM.md)** — the technical guide for following the code, QC, debugging, and maintenance: request lifecycle, module reference, debugging playbook, test map, operational tasks, and configuration reference.

See **[AI_CONTEXT.md](AI_CONTEXT.md)** — architectural map written for a future AI session that needs to extend this app.
