# Data Compass — AI Context

This document is written for a future AI session that needs to understand and extend this app. Read it before touching any code.

> For a **human-facing** technical guide (request lifecycle, debugging playbook,
> test map, operational tasks), see [CHARTROOM.md](CHARTROOM.md). This file is
> the architectural map; CHARTROOM is the hands-on maintenance manual.

---

## 1. Purpose

Data Compass is a **natural-language → SQL analytics web app** built as a portfolio piece. A user types a question in plain English; the app writes read-only SQL, executes it in-process via DuckDB, and returns the result table, an auto-generated chart, a short NL summary, and a cost transparency line.

The primary engineering showcase is **deliberate multi-tier LLM cost optimisation**: exact match → local FAISS semantic retrieval → cheap Haiku adjudication → expensive Sonnet generation, with SQL templates (not results) stored for reuse. The secondary showcases are GDPR-aware PII handling and ERD-guided multi-table queries.

---

## 2. Architecture Overview

```
app.py  (Streamlit entry point)
  │
  ├── src/data_compass/ui/          UI components (one file per view)
  │     landing.py                  Phase 1/9: title/tagline/subtitle + hero banner
  │     dataset_browser.py          Phase 2: dataset picker + table preview
  │     query.py                    Phase 3: question input + results
  │     results.py                  Phase 4: table + chart + summary + cost
  │     auth.py                     Phase 6: login/logout
  │     upload.py                   Phase 7: file upload
  │     pii_gate.py                 Phase 8: PII warning + mask consent
  │     legal.py                    Phase 8: ToS gate + privacy notice
  │     styles.py                   Phase 9: CSS + IBM Plex Sans injection
  │     about.py                    Phase 9: About / How this was made
  │     how_it_works.py             Phase 9: plain-English 5-step explainer
  │
  ├── src/data_compass/core/        Orchestration / pipelines
  │     query_flow.py               Phases 3–6: full query pipeline
  │
  ├── src/data_compass/llm/         LLM wrappers
  │     client.py                   Anthropic SDK wrapper
  │     sql_prompt.py               Schema-injected, cache-controlled prompt
  │     summary.py                  Short NL summary generation
  │
  ├── src/data_compass/cache/       Four-tier cache
  │     store.py                    SQLite schema for templates + embeddings
  │     exact.py                    Tier 1: normalised exact match
  │     semantic.py                 Tier 2: FAISS retrieval
  │     adjudicate.py               Tier 3: Haiku match + param extraction
  │     generate.py                 Tier 4: Sonnet generation + storage
  │
  ├── src/data_compass/data/        Dataset loading
  │     loader.py                   DuckDB loader + schema introspection
  │
  ├── src/data_compass/sql/
  │     guard.py                    Read-only SQL safety guard
  │
  ├── src/data_compass/viz/
  │     autochart.py                Plotly chart selection from result shape
  │
  ├── src/data_compass/auth/
  │     api_key.py                  BYOK session-only key handling
  │     store.py                    SQLite users + password hashing
  │     policy.py                   30-day password renewal
  │     recruiter.py                Temp login quota enforcement
  │     key_router.py               Resolve correct API key per user tier
  │
  ├── src/data_compass/erd/
  │     infer.py                    Local column-type inference
  │     build.py                    ERD from declared PK/FK
  │     validate.py                 Deterministic PK/FK validation
  │     plausibility.py             Haiku semantic plausibility check
  │
  ├── src/data_compass/pii/
  │     scan.py                     Deterministic PII detection
  │     mask.py                     PII masking before storage/API
  │     classify.py                 Haiku ambiguous-column classification
  │
  ├── src/data_compass/gdpr/
  │     consent.py                  Town/Postcode opt-in + withdrawal
  │     audit.py                    Detection/resolution audit log
  │
  ├── src/data_compass/assets/      Static visual assets
  │     logo.svg                    Compass rose + "DATA COMPASS" wordmark (for st.logo())
  │     logo_icon.svg               Compass rose only (collapsed sidebar icon)
  │     hero.svg                    SVG nautical-chart banner (built-in fallback)
  │     hero.png                    AI-generated hero (owner drop-in; overrides hero.svg)
  ├── src/data_compass/config.py    Central config + env overrides
  ├── src/data_compass/i18n.py      t(key) localisation helper
  │
  ├── .streamlit/config.toml        Streamlit theme (Chart Blue / Chart Paper / Brass)
  ├── locales/en-GB.json            All user-facing strings
  ├── data/registry.py              Demo dataset registry (REGISTRY list + get_dataset())
  ├── data/__init__.py              Package marker
  ├── data/prepare.py               Download + shape script (run once; idempotent)
  ├── data/land_registry/           UK Property Sales 2024 (OGL v3, HM Land Registry)
  │     transactions.csv            ~4,700 sales: uid, property_id, price, date, ppd_category
  │     properties.csv              ~4,714 unique properties: postcode, type, tenure, address, county
  └── data/weather/                 UK Weather Stations 1990–2026 (OGL v3, Met Office)
        stations.csv                18 stations: id, name, lat, lon, elevation, country, region
        observations.csv            ~7,500 monthly readings: tmax, tmin, af_days, rain_mm, sun_hours
```

---

## 3. Module Map (Phases 1–9)

| File | Responsibility |
|---|---|
| `app.py` | Entry point; `st.set_page_config` (🧭 favicon); `styles.inject()` (CSS/font); `st.logo()` (compass rose SVG); sidebar nav radio + dataset picker + BYOK input; routes to landing / dataset browser / query / account / upload / about / how-it-works |
| `src/data_compass/ui/styles.py` | `inject()` — injects IBM Plex Sans Google Font link + CSS overrides (block-container padding, heading weight, alert border-radius). Called once per render cycle from `app.py`. |
| `src/data_compass/ui/about.py` | `render()` — About / How this was made: portfolio caption; clean-room note; `/dev` skill note; tech stack list; GitHub link; Privacy Notice expander. |
| `src/data_compass/ui/how_it_works.py` | `render()` — 5-step plain-English explainer (choose dataset → ask → SQL generated/checked → results → cache), plus caching and synthetic-data notes in expanders. All text from locale. |
| `src/data_compass/config.py` | Model IDs, per-MTok USD rates, FX rate, cache settings; env overrides |
| `src/data_compass/i18n.py` | `t(key)` localisation helper |
| `src/data_compass/ui/landing.py` | Landing page — renders hero banner (hero.png preferred over hero.svg from `assets/`; base64-encoded img tag), then title, tagline, subtitle, choose-dataset CTA. |
| `src/data_compass/ui/dataset_browser.py` | `render_sidebar_picker()` + `render_browser(id)` — dataset selectbox + table schema/preview |
| `src/data_compass/ui/query.py` | `render_api_key_sidebar()` — BYOK password input; `render_query_panel(dataset_id)` — tier-aware key routing, recruiter quota, question input → `run_gated_query`; "Query your uploaded data" toggle (when ERD signed off); login-scoped upload cache |
| `src/data_compass/ui/auth.py` | `render_account_panel()` — Account tab: recruiter-token + admin login via `on_click` callbacks (no `st.rerun`), logged-in status + remaining quota + logout; writes tier to session via `key_router` |
| `src/data_compass/ui/upload.py` | `render_upload_panel()` — Upload tab: file uploader (CSV/XLSX ≤3), parse + store in `session_state["uploaded_files"]`; calls relationships form → validation → ERD sign-off; clears downstream state on new upload |
| `src/data_compass/ui/relationships.py` | `render_relationships_form(tables)` — PK selectbox per table + FK builder (4 selectboxes + Add/Remove); "Confirm schema" stores `ERDDeclaration` in `session_state["erd_declaration"]` |
| `src/data_compass/ui/erd_signoff.py` | `render_erd_signoff(declaration, validation)` — shows deterministic issues; "AI plausibility check" → Haiku; per-suggestion Accept/Keep; "Sign off ERD" → `session_state["erd_signed_off"]` |
| `src/data_compass/auth/api_key.py` | `set_key/get_key/clear_key/has_key(session)` — pure session-state logic; `render_sidebar_key_input()` — Streamlit widget |
| `src/data_compass/auth/store.py` | SQLite `users` table; Argon2id `hash_password`/`verify_password`; `create_user`, `set_password`, `seed_admin` (idempotent), `authenticate`; `User` dataclass |
| `src/data_compass/auth/policy.py` | `must_change_password(user)` + `password_age_days`/`days_until_renewal` — pure date logic, admins only, `now` injectable |
| `src/data_compass/auth/recruiter.py` | `recruiter_tokens` table; `create_recruiter_token` → `"<id>.<secret>"`; `verify_token` (Argon2), `check_access` (active/expiry/quota gate → `AccessResult`), `increment_usage`, `deactivate` |
| `src/data_compass/auth/key_router.py` | Session tier state (`TIER_PUBLIC/ADMIN/RECRUITER`, `login_admin/login_recruiter/logout/is_logged_in/get_recruiter_token_id`); `resolve_api_key` → `KeyResolution`; `get_upload_scope` → login-scoped cache scope for uploaded data |
| `src/data_compass/auth/resource.py` | `get_auth_conn()` — process-lifetime auth connection (`st.cache_resource`); `init_auth_db` seeds admin from env + ensures recruiter schema; patched in tests |
| `src/data_compass/data/loader.py` | `load_dataset(id)` → DuckDB connection; `get_schema(conn)` → `dict[table, list[ColumnInfo]]`; `load_uploaded_dataset(parsed_files)` → in-memory DuckDB from `ParsedFile` list; both loaders call `harden_connection` after CREATE TABLE (Step 8.0 sandbox) |
| `src/data_compass/upload/ingest.py` | `validate_file_count`, `validate_file_extension`, `parse_file` — CSV/XLSX parsing to DataFrame; `ParsedFile` dataclass |
| `src/data_compass/erd/infer.py` | `ColumnSchema`, `TableSchema`, `Relationship`, `ERDDeclaration` dataclasses; `infer_schema(name, df)` — dtype-based type inference; `table_name_from_filename` |
| `src/data_compass/erd/build.py` | `ERDGraph` dataclass; `build_erd(declaration)` — table lookup dict + FK adjacency list |
| `src/data_compass/erd/validate.py` | `ValidationIssue`, `ERDValidationResult`; `validate_erd(declaration, dfs)` — three deterministic checks: `pk_not_unique`, `fk_type_mismatch`, `fk_high_orphan_rate` (threshold 0.3) |
| `src/data_compass/erd/plausibility.py` | `PlausibilitySuggestion`; `check_plausibility(api_key, declaration)` → Haiku semantic review; `apply_decisions(declaration, suggestions, accepted)` — non-destructive apply |
| `src/data_compass/llm/sql_prompt.py` | `SYSTEM_INSTRUCTIONS` (cached); `build_schema_text(schema, entry)` → str; `build_schema_text_from_erd(schema, erd, name)` → str for uploaded data; `extract_sql(text)` → str |
| `src/data_compass/llm/client.py` | `generate_sql(api_key, schema_text, question)` → `(sql, Usage)` — direct (non-cached) Sonnet call; building block, not on the main path since Phase 5 |
| `src/data_compass/llm/summary.py` | `generate_summary(api_key, question, df)` → `(text\|None, Usage\|None)` — Haiku summary; returns (None, None) if df is empty |
| `src/data_compass/sql/guard.py` | `is_safe_sql(sql)` — SELECT-only check + DML/DDL block list + file/network-function & URL block (Step 8.0) + DuckDB parse validation; `harden_connection(conn)` — disables external access + locks config on a loaded connection (runtime sandbox) |
| `src/data_compass/viz/autochart.py` | `pick_chart(df)` → Plotly Figure or None — bar for low-cardinality category×numeric, line for date×numeric, None otherwise |
| `src/data_compass/cache/store.py` | SQLite template store: `connect`, `insert_template`, `get_by_exact_key`, `get_templates_for_dataset`, `set_summary`; `Template` dataclass; embedding (de)serialisation |
| `src/data_compass/cache/exact.py` | Tier 1 — `normalise(question)` + `lookup_exact(...)` (zero API) |
| `src/data_compass/cache/semantic.py` | Tier 2 — `embed_question` (local sentence-transformers, injectable) + `retrieve(query_vec, templates, top_k)` via FAISS cosine |
| `src/data_compass/cache/adjudicate.py` | Tier 3 — `adjudicate(api_key, question, candidates)` → `AdjudicationResult` (Haiku match + params, threshold-gated) |
| `src/data_compass/cache/generate.py` | Tier 4 — `generate_and_store(...)` → `GenerationResult` (Sonnet parameterised SQL, validated, stored only if executable); `substitute(template, params)` |
| `src/data_compass/cache/resource.py` | `get_cache_conn()` — process-lifetime shared cache connection (`st.cache_resource`); patched in tests |
| `src/data_compass/core/costing.py` | `compute_cost(usage, model)` → float (GBP); `build_cost_line([(model, usage)])` → `CostLine` with `.label` string |
| `src/data_compass/core/query_flow.py` | `QueryResult` dataclass; `run_query(..., schema_text=None)` — four-tier pipeline (skips registry if `schema_text` provided); `run_gated_query(session, auth_conn, …, schema_text=None)` — Phase 6 tier-aware wrapper |
| `src/data_compass/ui/results.py` | `render_results(result)` — SQL block + table + chart + summary + cache-tier/cost caption |
| `src/data_compass/pii/scan.py` | `PiiFinding`, `PiiScanResult`; `scan_dataframe(table, df)` / `scan_tables(dfs)` — deterministic local detection (email, UK postcode, UK phone, NINO, card via Luhn, DOB); one finding per column; no API |
| `src/data_compass/pii/mask.py` | `new_salt`, `mask_series`, `mask_dataframe(df, findings, *, salt)` — salted, one-way, letters-only pseudonyms; deterministic under a shared salt (joins survive; re-scan finds nothing) |
| `src/data_compass/pii/classify.py` | `ColumnClassification`, `ClassificationResult`; `find_ambiguous_columns(df, scan)`; `classify_ambiguous_columns(api_key, table, df, scan)` — one Haiku call on a minimal truncated sample; no call when nothing ambiguous |
| `src/data_compass/gdpr/consent.py` | `ConsentRecord`; `grant_consent`/`withdraw_consent`/`has_consent`/`get_consent` — Town/Postcode opt-in in the auth DB (append-only trail); subject = `key_router.get_upload_scope` |
| `src/data_compass/gdpr/audit.py` | `Detection`, `AuditEntry`, `RESOLUTION_*`; `log_detection(...)` / `get_entries(conn, subject)` — append-only, value-free PII detection/resolution log in the auth DB |
| `src/data_compass/ui/pii_gate.py` | `render_pii_gate(stored)` (block→report→consent→mask, logs audit) + `render_consent_withdrawal()` (re-mask + drop cache + log) |
| `src/data_compass/ui/legal.py` | `render_tos_gate()` (blocks upload until accepted), `render_privacy_notice()`, `render_caching_warning()` |
| `data/registry.py` | `REGISTRY` list; `get_dataset(id)` |
| `data/prepare.py` | One-shot data download + reshape script |
| `locales/en-GB.json` | All UI strings: `app.*`, `landing.*`, `sidebar.*`, `dataset_browser.*`, `query.*`, `upload.*`, `pii.*`, `legal.*`, `relationships.*`, `erd_signoff.*`, `about.*`, `how_it_works.*`, `errors.*` |
| `.streamlit/config.toml` | Streamlit theme: `primaryColor=#1B6CA8`, `backgroundColor=#F7F9FC`, `secondaryBackgroundColor=#E8EFF7`, `textColor=#1C2B3A`, `font=sans serif` |
| `src/data_compass/assets/logo.svg` | Compass rose + "DATA COMPASS" wordmark. Used by `st.logo(image=…)`. Cardinal arrows (N dark navy, S/E/W chart blue), brass intercardinal lines, brass centre pin. viewBox 200×52. |
| `src/data_compass/assets/logo_icon.svg` | Compass rose only (no text). Used by `st.logo(icon_image=…)` for the collapsed sidebar. viewBox 50×52. |
| `src/data_compass/assets/hero.svg` | Built-in SVG hero banner: nautical chart grid, depth contours, coordinate labels, depth soundings, compass rose. viewBox 900×150. Rendered by `landing.py`. |
| `src/data_compass/assets/hero.png` | Optional AI-generated hero image (owner drop-in). `landing.py` prefers this over `hero.svg` when present. |

---

## 4. Data Flow (Phase 2)

```
streamlit run app.py
  → set_page_config
  → sidebar: nav radio + render_sidebar_picker()
      → selectbox writes session_state["selected_dataset_id"]
  → if nav == "Datasets" and dataset selected:
        render_browser(dataset_id)
          → get_dataset(id)           # registry lookup
          → _cached_load(id)          # st.cache_resource → load_dataset()
              → duckdb.connect(":memory:")
              → CREATE TABLE t AS SELECT * FROM read_csv_auto(path)  [per table]
          → get_schema(conn)          # information_schema introspection
          → st.header / expander / st.dataframe per table
    else:
        render_landing()

Phase 3+ adds: question → query_flow.py → cache pipeline → LLM → SQL guard → DuckDB → results panel.
```

---

## 5. Key Design Decisions

**Localisation from day one.** Every user-facing string goes through `t()`. No hard-coded UI text anywhere. This makes the no-hard-coded-strings test meaningful and keeps future translation trivial.

**`t()` never raises.** Missing keys return `[missing: key]` — the UI always renders, tests catch the gap.

**Config via env overrides, not a config file.** `config.py` reads env vars at import time (after `load_dotenv`). Reloading the module in tests is how you test overrides.

**Rates in USD, displayed in GBP.** All monetary computation happens in USD (matching the Anthropic API). `FX_USD_TO_GBP` is applied at display time only. This keeps the cost accounting clean and the FX concern isolated to the UI layer.

**SQL templates stored, not results.** The cache stores parameterised SQL templates so data changes are always reflected. Re-executing the template on each hit is intentional.

**Deterministic before AI, always.** PII scan → deterministic validation → cheap Haiku → expensive Sonnet. Every phase that touches AI has a free local path tried first.

**The LLM is untrusted; the SQL guard is the trust boundary.** The model's only privileged output is SQL, which is re-validated by `is_safe_sql()` on *every* cache tier before execution. Prompt injection (direct or indirect via data) therefore cannot escalate beyond a read-only `SELECT` on the user's own connection. Prompt-level "ignore injections" wording is never relied on as a control. **Step 8.0 closed the file-read gap:** the guard now also blocks DuckDB file/network table functions (`read_csv`, `read_text`, `read_parquet`, `glob`, …) and remote URL schemes inside a `SELECT`, and `harden_connection()` disables `enable_external_access` + locks the configuration on every loaded connection — so even a text-match miss cannot read outside the loaded in-memory tables. Untrusted schema/result content is also wrapped in explicit data-only delimiters (defence in depth, not the boundary).

**Owner key never reaches the public tier.** `resolve_api_key` returns the owner key only for admin/recruiter sessions; public visitors always get their own BYOK key (or none). Recruiter abuse of the owner key is bounded by the quota gate, enforced *before* any API call in `run_gated_query`.

**Mask before anything leaves the gate (Phase 8).** The upload flow is ordered ToS gate → PII scan/gate → previews/schema/ERD/query. The PII gate blocks the journey on detection and masks (or retains-under-consent) *before* any preview, prompt or cache write — so raw personal data never reaches a prompt or the shared cache. Masks are one-way and letters-only by construction, so they cannot themselves match any detector. Consent (Town/Postcode retain) and the detection/resolution audit log are durable, per-user, value-free, in the auth DB. Legal text is DRAFT (locale + `docs/PRIVACY_NOTICE.md`), to be reviewed before public deploy; controller named per owner steer.

**Login via `on_click` callbacks, not `st.rerun()`.** Callbacks run before the script re-executes, so the rendered Account view is consistent within one run and the flow is clean under AppTest (which mishandles widgets that disappear across an `st.rerun()`).

---

## 6. Extension Points

- **New locale:** add `locales/<tag>.json` mirroring `en-GB.json`; pass the tag to `t(key, locale=tag)`.
- **New UI page:** add a file to `src/data_compass/ui/`, import and call in `app.py` based on `st.session_state.nav_selection`.
- **New model/rate:** add an entry to `MODEL_RATES` in `config.py` — the cost accounting picks it up automatically.
- **New dataset:** add files to `data/` and register in `data/registry.py` (Phase 2).

---

## 7. Localisation Architecture

`locales/en-GB.json` is a nested JSON object. Keys are dot-separated paths (`app.nav.datasets`). The `t()` helper in `i18n.py` walks the nesting. The module-level `_cache` dict memoises parsed files. Call `_cache.clear()` in tests to force a reload.

---

## 8. Current Limitations (Phase 9 near-complete — deploy config remaining)

- **Phases 1–8 complete.** Phase 9 visual identity (9.0), About (9.1), How it works (9.2), and README/AI_CONTEXT (9.3) are done. Remaining: deploy configuration (9.4 — owner-performed).
- **Phase 8 (PII failsafe & GDPR surfaces) is complete:** deterministic scan (8.1), block-and-warn + mask-before-API (8.2), ambiguous-column Haiku classification (8.3), Town/Postcode consent + withdrawal (8.4), ToS gate + privacy notice + caching warning (8.5), detection/resolution audit log (8.6).
- **Legal text is DRAFT.** `docs/PRIVACY_NOTICE.md` and the `legal.*` locale strings are clearly marked "not legal advice"; they must be reviewed before public deployment. Controller is named per owner steer (Giacomo Carboni / giacomo.carboni@gmail.com).
- **PII detection is heuristic.** The deterministic scan covers email/UK postcode/UK phone/NINO/card(Luhn)/DOB with a value-rate + name-hint policy; free-text personal data (names/addresses) relies on the optional Haiku escalation, which is not auto-wired into the gate (the module stands alone — the gate masks only deterministically-detected columns).
- **Step 8.0 (SQL & AI execution hardening) is complete:** the guard blocks file/network functions + URLs, and `harden_connection()` sandboxes every loaded connection (no external filesystem/HTTP access, config locked). Uploaded column names and cell values still flow into prompts (indirect prompt injection), but the guard + sandbox bound the blast radius to a read-only `SELECT` over the loaded tables, and untrusted content is delimiter-wrapped; PII masking now further shrinks what is sent.
- The DuckDB connection for uploaded data is stored in `session_state["_uploaded_duckdb_conn"]` (session-lifetime); it is recreated automatically if missing. Clearing it is safe — it is rebuilt from the stored `ParsedFile` list.
- Uploaded data stays in memory only; it is never written to disk or shared across sessions.
- Demo-dataset queries run at `public` cache scope; uploaded-data queries use a login-scoped key (`upload:admin:<username>` / `upload:recruiter:<token_id>`) so they never pollute the shared demo cache.
- The recruiter access token and admin login are kept in `st.session_state` only for the session; the login input keys are cleared after a successful login.
- The cache is shared across all visitors at `public` scope (a single SQLite file).
- A Tier-1 exact hit reuses the cached summary, which was generated against the data as it was at store time. With the static demo data this is always accurate; for live-changing data the summary could drift (the SQL is always re-executed, so the table itself stays fresh).
- Tier-3 adjudication trusts Haiku's extracted parameter values; they are substituted into the template and then re-validated by the safety guard, but malformed extractions surface as a query error rather than a silent fallback to Sonnet.
- `client.generate_sql` is retained as a building block but is no longer on the main query path (Tier 4 `generate_and_store` supersedes it).
- `_cached_load` and `get_cache_conn` use `st.cache_resource` (process-lifetime); a dataset/cache file refresh needs a server restart.
- The BYOK key is held in `st.session_state`; it is lost when the browser tab closes (by design — never persisted).
- Auto-chart shows at most one chart per result (first categorical×numeric or date×numeric pair).

---

## 9. Open Questions

- FX rate is hardcoded at 0.79 and overridable via env. Consider fetching from an exchange-rate API on startup in a later phase (but keep it optional — the app must work offline).
- The GitHub repo URL in `locales/en-GB.json` (`about.repo_url`) is a placeholder — update it to the real URL before public deploy.
- The hero banner SVG is a clean-room placeholder. The owner may drop a `hero.png` (AI-generated) into `src/data_compass/assets/` to replace it; `landing.py` prefers PNG automatically.
- Legal text (`docs/PRIVACY_NOTICE.md` and `legal.*` locale strings) is DRAFT — must be reviewed by a qualified professional before public deployment.
