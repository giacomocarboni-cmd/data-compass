# The Chartroom — Data Compass Technical Guide

> The chartroom is where a navigator studies the charts and plots the route.
> This is that room for the codebase: a hands-on guide for a human doing QC,
> debugging, and maintenance — no AI assistant required.

**This is a living document.** It is updated at every phase boundary alongside
the code. If you change how a request flows, where a module sits, or how to
debug something, update the relevant section here in the same change.

- **Last updated:** 2026-06-22 (end of Phase 9 — Visual Identity, About/How-it-Works, Deploy Config)
- **Companion docs:** [README.md](README.md) (end users) ·
  [AI_CONTEXT.md](AI_CONTEXT.md) (architecture map for an AI session) ·
  [PLAN.md](../PLAN.md) (phased build plan + test criteria)
- **Path convention:** all `src/...`, `app.py`, `tests/...` paths below are
  relative to the **project root** (`Data Compass/`).

---

## 1. The 30-second mental model

A user types a plain-English question. The app:

1. Tries to answer it **from a cache** of previously-generated SQL (cheapest
   first: exact text → semantic similarity → cheap-model adjudication).
2. Only on a genuine miss does it pay for the **expensive model (Sonnet)** to
   write fresh SQL, which it then stores for next time.
3. The SQL is **safety-checked** (read-only), run **in-process by DuckDB**, and
   the result is shown as a **table + chart + plain-English summary + a cost
   line** stating exactly which AI models ran and what they cost.

Everything the user sees goes through a **localisation layer** (`t()`), and the
user's API key lives **only in session memory**, never on disk.

---

## 2. Architecture at a glance

The code is organised in **layers**. Dependencies point downward — UI calls
core, core calls the cache/LLM/sql/viz building blocks, those call data + config.

```
            +------------------------------------------------------+
ENTRY       | app.py   -   Streamlit page, sidebar, routing        |
            +---------------------------+--------------------------+
                                        ▼
            +------------------------------------------------------+   src/data_compass/ui/
UI          | landing / dataset_browser / query / results / auth   |   one file per screen;
            +---------------------------+--------------------------+   only this layer imports streamlit
                                        ▼
            +------------------------------------------------------+   src/data_compass/core/
CORE        | query_flow   -   four-tier pipeline + gated wrapper  |   orchestration; no streamlit
            | costing      -   cost accounting (USD->GBP)          |
            +---------------------------+--------------------------+
                                        ▼
            +------------------------------------------------------+   src/data_compass/{cache,llm,sql,viz,auth}/
BUILDING    | cache/        -   the four cache tiers               |
            | llm/          -   Anthropic API wrappers             |
            | sql/ + viz/   -   safety guard + auto-chart          |
            | auth/         -   users, recruiter tokens, tiers     |
            +---------------------------+--------------------------+
                                        ▼
            +------------------------------------------------------+   src/data_compass/{data,config,i18n}.py
FOUNDATION  | data.loader + registry   -   DuckDB load + datasets  |
            | config + i18n            -   settings + localisation |
            +------------------------------------------------------+
```

**Golden rule:** only the UI layer imports `streamlit`. Core and building
blocks are plain Python, which is why they're easy to unit-test without a
running app.

---

## 3. Follow the flow — a question's journey through the code

This is the single most useful thing to know for debugging. Trace it top to
bottom; each arrow is a real call you can breakpoint.

```
USER presses "Ask"
  │
  ▼  app.py:47        nav routes to the Query screen
render_query_panel()              ui/query.py:50
  │  - guards: dataset selected? key entered?   ui/query.py:58-65
  │  - reads the question box + Ask button       ui/query.py:69-75
  │  - loads the dataset (cached DuckDB conn)     ui/query.py:78  → ui/dataset_browser.py _cached_load
  │  - gets the shared cache connection           ui/query.py:79  → cache/resource.py:21 get_cache_conn()
  ▼
run_query(question, dataset_id, api_key, duck_conn, cache_conn)   core/query_flow.py:102
  │
  ├─ build schema text for the prompt            query_flow.py:118-120
  │
  ├─ TIER 1  exact / normalised text match       query_flow.py:123  → cache/exact.py:34 lookup_exact
  │     hit → reuse SQL + cached summary, ZERO API, return        (cache_tier="exact")
  │
  ├─ TIER 2+3  (only if cache has templates)      query_flow.py:136
  │     embed the question locally               → cache/semantic.py:40 embed_question  (no API)
  │     FAISS top-K similar templates            → cache/semantic.py:57 retrieve        (no API)
  │     Haiku judges the best candidate + params → cache/adjudicate.py:71 adjudicate    (cheap API)
  │     matched & confident → reuse template, substitute params, return (cache_tier="semantic")
  │
  └─ TIER 4  miss → Sonnet writes new SQL         query_flow.py:153 → cache/generate.py:86 generate_and_store
        parameterised SQL + param defs (expensive API)
        validate: safety guard + DuckDB parse, then STORE w/ embedding   (cache_tier="miss")
  │
  ▼  _finalise()  query_flow.py:59   (shared tail for every tier)
     ├─ is_safe_sql(sql)             sql/guard.py:38      read-only gate
     ├─ duck_conn.execute(sql)       query_flow.py:71     run it
     ├─ pick_chart(df)               viz/autochart.py:40  choose bar/line/none
     ├─ generate_summary(...)        llm/summary.py:28    Haiku paragraph (skipped if summary reused)
     └─ build_cost_line(usages)      core/costing.py:62   "Sonnet + Haiku · £0.00XX"
  │
  ▼  result stored in st.session_state["query_result"]   ui/query.py:82
render_results(result)              ui/results.py:35
     SQL block · table · chart · summary · cache-tier + cost caption
```

**Reading tip:** the four tiers live *inside* `run_query`. If you want to know
"why did this question cost money / hit the cache / pick that template," set a
breakpoint at [query_flow.py](../src/data_compass/core/query_flow.py) `run_query`
and step through. The `cache_tier` field on the returned `QueryResult` tells you
which path won.

**Phase 6 — the gate sits in front.** Since Phase 6 the UI calls
`run_gated_query()` (not `run_query` directly). It wraps the pipeline with:

```
run_gated_query()                 core/query_flow.py
  ├─ resolve_api_key(session)     auth/key_router.py   public→BYOK, admin/recruiter→owner
  ├─ if recruiter:                                     gate BEFORE any API call
  │     get_token + check_access  auth/recruiter.py    active AND not expired AND under cap?
  │     blocked → QueryResult(cache_tier="blocked", error="blocked:<reason>")   ZERO API
  ├─ if no key for this tier → QueryResult(error="no_key")
  ├─ run_query(...)                                    the four tiers above
  └─ if recruiter and result.error is None:
        increment_usage(...)      auth/recruiter.py    one query consumed (even a cache hit)
```

A `cache_tier == "blocked"` result is rendered by `_render_blocked` in
[ui/query.py](../src/data_compass/ui/query.py) as a localised message; no SQL and
no cost line are shown because nothing ran. Login itself happens on the **Account**
screen ([ui/auth.py](../src/data_compass/ui/auth.py)) via `on_click` callbacks
that set the session tier — never `st.rerun()` (which AppTest mishandles).

---

## 4. Module reference

Grouped by layer. Each module's source file opens with a docstring giving more
detail — this table is the index.

### Entry & UI (`src/data_compass/ui/`, `app.py`)

| Module                  | Job                                                                                                                               | Key symbols                                                             |
|-------------------------|-----------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| `app.py`                | Page config; `styles.inject()` (CSS/font); `st.logo()` (SVG compass); sidebar nav + dataset picker + BYOK; routes all pages       | `nav` radio, routing block                                              |
| `ui/landing.py`         | Welcome screen: base64 hero banner (hero.png preferred, hero.svg fallback) + title/tagline/CTA                                    | `render()`, `_hero_html()`                                              |
| `ui/styles.py`          | CSS + IBM Plex Sans font injection; padding and heading-weight overrides                                                          | `inject()`                                                              |
| `ui/about.py`           | About page: portfolio note, clean-room note, `/dev` skill, stack, GitHub link, Privacy Notice expander                            | `render()`                                                              |
| `ui/how_it_works.py`    | 5-step plain-English explainer + caching and data-source notes in expanders; all text from locale                                 | `render()`                                                              |
| `ui/dataset_browser.py` | Dataset picker + per-table schema/preview                                                                                         | `render_sidebar_picker()`, `render_browser()`, `_cached_load()`         |
| `ui/query.py`           | Question input + Ask; tier-aware key routing + recruiter quota gate; "Query your uploaded data" toggle; calls the gated pipeline  | `render_query_panel()`, `render_api_key_sidebar()`, `_render_blocked()` |
| `ui/auth.py`            | Account screen: recruiter-token + admin login (`on_click` callbacks); status + remaining quota + logout                           | `render_account_panel()`, `_cb_recruiter_login()`, `_cb_admin_login()`  |
| `ui/upload.py`          | Upload tab: file uploader (CSV/XLSX ≤3); parse → relationships form → validation → sign-off; clears state on new upload          | `render_upload_panel()`                                                 |
| `ui/relationships.py`   | PK selectbox per table + FK builder form; "Confirm schema" stores `ERDDeclaration` in session                                     | `render_relationships_form()`, `_cb_add_fk()`, `_store_declaration()`  |
| `ui/erd_signoff.py`     | Deterministic-issue warnings; "AI plausibility check" button; per-suggestion Accept/Keep; "Sign off ERD"                         | `render_erd_signoff()`, `_cb_accept()`, `_cb_reject()`, `_cb_sign_off()` |
| `ui/results.py`         | Render SQL + table + chart + summary + cost caption                                                                               | `render_results()`, `_cost_caption()`                                   |

### Core orchestration (`src/data_compass/core/`)

| Module               | Job                                                                             | Key symbols                                       |
|----------------------|---------------------------------------------------------------------------------|---------------------------------------------------|
| `core/query_flow.py` | Four-tier pipeline + Phase 6 gated wrapper; never raises, returns `QueryResult` | `run_query()`, `run_gated_query()`, `QueryResult` |
| `core/costing.py`    | Convert token `usage` → £; build the model/cost label                           | `compute_cost()`, `build_cost_line()`, `CostLine` |

### The four-tier cache (`src/data_compass/cache/`)

| Tier  | Module                | Job                                                            | API cost               |
|-------|-----------------------|----------------------------------------------------------------|------------------------|
| store | `cache/store.py`      | SQLite template store (SQL, params, embedding, summary, scope) | —                      |
| 1     | `cache/exact.py`      | Normalise question text → direct lookup                        | **none**               |
| 2     | `cache/semantic.py`   | Local embedding + FAISS top-K retrieval                        | **none** (local model) |
| 3     | `cache/adjudicate.py` | Haiku confirms a candidate + extracts params                   | cheap                  |
| 4     | `cache/generate.py`   | Sonnet writes parameterised SQL, validate + store              | expensive              |
| —     | `cache/resource.py`   | Process-lifetime shared cache connection                       | —                      |

### LLM, SQL safety, charts (`src/data_compass/{llm,sql,viz}/`)

| Module              | Job                                                                      | Key symbols                                                   |
|---------------------|--------------------------------------------------------------------------|---------------------------------------------------------------|
| `llm/client.py`     | Direct Sonnet SQL call (building block; off the main path since Phase 5) | `generate_sql()`                                              |
| `llm/sql_prompt.py` | System instructions + schema text + SQL extraction                       | `SYSTEM_INSTRUCTIONS`, `build_schema_text()`, `extract_sql()` |
| `llm/summary.py`    | Haiku one-paragraph result summary                                       | `generate_summary()`                                          |
| `sql/guard.py`      | Read-only gate: SELECT-only + block list + file/network-fn & URL block + DuckDB parse; connection sandbox | `is_safe_sql()`, `harden_connection()`     |
| `viz/autochart.py`  | Choose a chart from result shape                                         | `pick_chart()`                                                |

### Authentication & tiers (`src/data_compass/auth/`)

| Module               | Job                                                                     | Key symbols                                                                 |
|----------------------|-------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| `auth/api_key.py`    | BYOK key in session memory only (never disk/logs)                       | `set_key/get_key/has_key/clear_key`                                         |
| `auth/store.py`      | SQLite `users`; Argon2id hashing; idempotent admin seed                 | `hash_password`, `verify_password`, `seed_admin`, `authenticate`            |
| `auth/policy.py`     | Admin password renewal age (default 30 days); pure date logic           | `must_change_password`, `password_age_days`                                 |
| `auth/recruiter.py`  | Recruiter tokens `id.secret`; active/expiry/quota gate; usage count     | `create_recruiter_token`, `verify_token`, `check_access`, `increment_usage` |
| `auth/key_router.py` | Session tier state; route key per tier (public->BYOK, logged-in->owner) | `resolve_api_key`, `login_admin/recruiter`, `logout`                        |
| `auth/resource.py`   | Process-lifetime auth connection; seeds admin + recruiter schema        | `get_auth_conn()` (`st.cache_resource`)                                     |

### Upload & ERD (`src/data_compass/{upload,erd}/`)

| Module               | Job                                                                                            | Key symbols                                                          |
|----------------------|------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| `upload/ingest.py`   | File validation + CSV/XLSX parsing; `ParsedFile` dataclass                                     | `validate_file_count()`, `validate_file_extension()`, `parse_file()` |
| `erd/infer.py`       | dtype-based column type inference; ERD dataclasses                                             | `infer_schema()`, `ColumnSchema`, `TableSchema`, `ERDDeclaration`    |
| `erd/build.py`       | Build FK adjacency graph from declaration                                                      | `build_erd()`, `ERDGraph`                                            |
| `erd/validate.py`    | Three deterministic checks: PK uniqueness, FK type match, FK orphan rate (threshold 0.3)       | `validate_erd()`, `ERDValidationResult`, `ValidationIssue`           |
| `erd/plausibility.py`| Haiku semantic review; non-destructive apply of suggestions                                    | `check_plausibility()`, `apply_decisions()`, `PlausibilitySuggestion`|

### PII failsafe & GDPR (`src/data_compass/{pii,gdpr}/`, `ui/{pii_gate,legal}.py`)

The upload journey is ordered **ToS gate → PII scan/gate → previews/schema/ERD/query**, so raw personal data is masked (or retained under consent) before it can reach a preview, a prompt or the shared cache.

| Module          | Job                                                                                          | Key symbols                                                                |
|-----------------|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| pii/scan.py     | Deterministic local detection (email, UK postcode/phone, NINO, card via Luhn, DOB); no API   | `scan_dataframe()`, `scan_tables()`, `PiiFinding`, `PiiScanResult`         |
| pii/mask.py     | Salted, one-way, letters-only pseudonyms; deterministic under a shared salt (joins survive)  | `new_salt()`, `mask_dataframe()`, `mask_series()`                          |
| pii/classify.py | Escalate only ambiguous text columns to Haiku on a minimal truncated sample; no call if none | `find_ambiguous_columns()`, `classify_ambiguous_columns()`                 |
| gdpr/consent.py | Town/Postcode retain-with-consent in the auth DB (append-only trail); withdrawal             | `grant_consent()`, `withdraw_consent()`, `has_consent()`                   |
| gdpr/audit.py   | Append-only, value-free PII detection/resolution log in the auth DB                          | `log_detection()`, `get_entries()`, `RESOLUTION_*`                         |
| ui/pii_gate.py  | Block->report->consent->mask gate; logs audit; consent-withdrawal control                    | `render_pii_gate()`, `render_consent_withdrawal()`                         |
| ui/legal.py     | ToS gate (blocks upload), Privacy Notice (DRAFT), caching warning                            | `render_tos_gate()`, `render_privacy_notice()`, `render_caching_warning()` |

### Foundation (`src/data_compass/{data,config,i18n}.py`, `data/`)

| Module             | Job                                                                    | Key symbols                                       |
|--------------------|------------------------------------------------------------------------|---------------------------------------------------|
| `data/loader.py`   | Load demo dataset into DuckDB; load uploaded files; introspect schema  | `load_dataset()`, `get_schema()`, `load_uploaded_dataset()` |
| `data/registry.py` | The demo dataset catalogue (paths, schema hints, licence)              | `REGISTRY`, `get_dataset()`                       |
| `data/prepare.py`  | One-shot script to download + reshape the demo CSVs                    | run manually                                      |
| `config.py`        | Model IDs, per-MTok rates, FX, cache settings, paths                  | `MODEL_*`, `MODEL_RATES`, `FX_USD_TO_GBP`         |
| `i18n.py`          | `t(key)` localisation; never raises                                    | `t()`                                             |

---

## 5. The four-tier cache, in plain terms

This is the app's headline engineering feature, so it's worth understanding well.

- **What is stored:** *templates*, not answers. A template is a **parameterised
  SQL statement** (e.g. `... WHERE price > {min_price}`) plus the parameter
  definitions, a local **embedding** of the original question, and (for exact
  hits) the **summary text**. Because the SQL is re-executed on every hit, the
  *data* in the result is always current even though the SQL is reused.

- **Why tiered:** each tier is cheaper than the next. We try free text matching,
  then free local-vector similarity, then a cheap model, and only reach the
  expensive model when nothing else works. The cost caption makes this visible.

- **The pay-off you can see:** ask a question (caption shows
  `Freshly generated · Sonnet + Haiku · £0.00XX`), then ask it again
  (`Served from cache (exact match) · No AI used · £0.0000`).

- **Scope isolation:** every template has a `scope` (`"public"` by default).
  This is the seam for Phase 6/7 to keep a logged-in user's uploaded-dataset
  templates separate from the shared demo cache. Not yet wired to logins.

- **Trust rule:** a template is only stored if its SQL **passed the safety guard
  and actually executed** ([generate.py:122-133](../src/data_compass/cache/generate.py#L122)).
  A cache hit therefore re-runs SQL we already proved valid.

### Authentication, tiers & quota (plain terms)

Phase 6 adds three **tiers**, decided per session and held in `st.session_state`:

- **Public** (default) — anyone. Brings their **own** Anthropic key (BYOK), held
  in session memory only. This is the open demo experience.
- **Recruiter** — logs in on the **Account** screen with a one-off **access
  token** (`"<id>.<secret>"`). Uses the **owner's** key, capped at 20 queries /
  30 days (configurable). The cap is a *usage* quota: every successful query
  counts, including zero-cost cache hits.
- **Admin** — username + password (the admin is **seeded from the environment**
  on first run). Uses the owner's key; the password is flagged for renewal after
  30 days.

Two rules make this safe:

1. **The owner key never reaches a public visitor.** `resolve_api_key`
   ([auth/key_router.py](../src/data_compass/auth/key_router.py)) returns the
   owner key only for admin/recruiter; public always gets BYOK (or nothing).
2. **The recruiter gate runs before any API call.** `run_gated_query` checks
   `check_access` *first*; a blocked token returns a `cache_tier="blocked"`
   result with zero spend. The counter only advances on a successful query.

**Tokens & passwords are never stored in the clear** — Argon2id hashes only. A
recruiter token's plaintext is shown **once** at creation and is unrecoverable
after; the secret half is verified against the stored hash, located by the `id`
prefix (salted hashes can't be looked up by value).

**Security boundary worth remembering:** the LLM is treated as **untrusted**. Its
only privileged output is SQL, re-validated by `is_safe_sql` on every tier, so
prompt injection can't escalate beyond a read-only `SELECT`. **Step 8.0 closed
the file-read gap:** the guard now also blocks DuckDB file/network functions
(`read_text`, `read_csv`, `glob`, …) and remote URLs, and `harden_connection()`
disables external access + locks the config on every loaded connection — so even
a guard miss cannot read outside the loaded in-memory tables. Untrusted
schema/result text is delimiter-wrapped in prompts (defence in depth, not the
boundary).

---

## 6. Debugging playbook

Symptom → where to look first.

| Symptom                                             | Likely cause & first place to look                                                                                                                                                                                                                                             |
|-----------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Empty SQL / "Could not parse generated SQL"**     | The model returned non-JSON. Check `_parse_response` in [generate.py:61](../src/data_compass/cache/generate.py#L61); inspect the raw `response.content[0].text`. In tests, a mock returning the *wrong* payload (e.g. summary text routed to the generator) causes this.       |
| **Cache never hits on a repeat**                    | (a) Question text differs after `normalise()` — check [exact.py:25](../src/data_compass/cache/exact.py#L25). (b) `get_cache_conn()` returning a fresh DB each call — check [resource.py:21](../src/data_compass/cache/resource.py#L21). (c) Different `dataset_id` or `scope`. |
| **Semantic tier never fires**                       | It's skipped when the cache has no templates ([query_flow.py:136](../src/data_compass/core/query_flow.py#L136)). Confirm at least one template is stored (`store.count_templates`).                                                                                            |
| **Wrong / missing chart**                           | `pick_chart` rules: needs ≥2 cols, a numeric col, plus a low-cardinality category (bar) or a date (line). See [autochart.py:40](../src/data_compass/viz/autochart.py#L40). Pandas 3.0 strings are `StringDtype`, not `object` — date detection relies on `is_string_dtype`.    |
| **Cost shows £0.00 unexpectedly**                   | Either a true cache hit (`cache_tier == "exact"`) or an unknown model id in `MODEL_RATES` ([costing.py:46](../src/data_compass/core/costing.py#L46)). Check the model id matches `config.py`.                                                                                  |
| **"not safe to execute" on valid-looking SQL**      | The guard blocks anything that isn't a single SELECT/WITH, or contains a blocked keyword, or fails DuckDB's parser. See [guard.py:38](../src/data_compass/sql/guard.py#L38).                                                                                                   |
| **`[missing: some.key]` in the UI**                 | A `t()` key is referenced but absent from `locales/en-GB.json`. Add it.                                                                                                                                                                                                        |
| **Query errors with "Binder Error: ... not found"** | The generated SQL references a column/table that isn't in the schema. Cross-check against `data/registry.py` schema hints and `get_schema()`.                                                                                                                                  |
| **App won't import a module**                       | Run `pip install -e .` from the project root; the package is `data_compass`.                                                                                                                                                                                                   |
| **Recruiter blocked immediately / unexpectedly**    | `check_access` in [recruiter.py](../src/data_compass/auth/recruiter.py): inspect `active`, `expires_at`, `queries_used` vs `query_cap`. `result.error` is `blocked:expired` / `blocked:quota_exceeded` / `blocked:inactive`. `access_revoked` means the token row is gone.     |
| **Logged-in query says "owner key not configured"** | `ANTHROPIC_API_KEY` is unset, so `resolve_api_key` returns no owner key for the tier. Set it in `.env` (or `st.secrets` on deploy).                                                                                                                                            |
| **Admin can't log in after first run**              | Admin is seeded only if `ADMIN_PASSWORD` was set when `auth.db` was first created. Delete `cache/auth.db` and restart with `ADMIN_PASSWORD` set, or add the user via `auth.store.create_user`.                                                                                 |
| **Login button "does nothing" in a test**           | Login uses `on_click` callbacks, not `st.rerun()`. In AppTest, set the input then `button.click().run()`; assert via `session_state["auth_tier"]`. Patch `auth.resource.get_auth_conn` to an in-memory store.                                                                  |

**General technique:** because `run_query` never raises, failures surface as
`QueryResult.error`. Inspect `result.error` and `result.cache_tier` first —
they tell you *which tier* produced the problem before you dig into any module.

---

## 7. Test map

~460 tests, all Anthropic API calls mocked (no live spend). One opt-in test
exercises the real local embedder.

| Test file                    | Guards                                                             | Count  |
|------------------------------|--------------------------------------------------------------------|--------|
| `test_landing.py`            | App boots; landing screen localised                                | 5      |
| `test_i18n.py`               | `t()` resolution + missing-key marker                              | 7      |
| `test_config.py`             | Rates/threshold + env overrides                                    | 5      |
| `test_loader.py`             | DuckDB load + schema introspection                                 | 13     |
| `test_step_2_1.py`           | Dataset registry + bundled CSV integrity                           | 13     |
| `test_step_2_3.py`           | Dataset picker + browser UI                                        | 7      |
| `test_sql_prompt.py`         | Prompt assembly + SQL extraction                                   | 18     |
| `test_guard.py`              | Read-only safety guard + file/network-fn & URL block (Step 8.0)    | 40     |
| `test_sql_sandbox.py`        | Connection sandbox: file reads blocked, loaded tables queryable    | 6      |
| `test_step_3_4.py`           | **Phase 3 journey:** ask → SQL + table                             | 7      |
| `test_autochart.py`          | Chart-type selection                                               | 10     |
| `test_summary.py`            | Haiku summary; skip on empty                                       | 7      |
| `test_costing.py`            | £ computation + cost line                                          | 13     |
| `test_step_4_4.py`           | **Phase 4 journey:** table + chart + summary + cost                | 9      |
| `test_cache_store.py`        | SQLite template round-trip + scoping                               | 11     |
| `test_exact.py`              | Tier 1 normalise + lookup                                          | 11     |
| `test_semantic.py`           | Tier 2 FAISS retrieval (+1 opt-in real model)                      | 6 (+1) |
| `test_adjudicate.py`         | Tier 3 Haiku adjudication                                          | 9      |
| `test_generate.py`           | Tier 4 generate + store/validate                                   | 10     |
| `test_step_5_6.py`           | **Phase 5 journey:** miss → store → exact hit (zero cost)          | 7      |
| `test_api_key.py`            | BYOK session-only handling                                         | 11     |
| `test_auth_store.py`         | Argon2id hashing + admin seed + authenticate                       | 14     |
| `test_policy.py`             | Admin 30-day password renewal (pure date logic)                    | 10     |
| `test_recruiter.py`          | Recruiter tokens: verify + active/expiry/quota gate                | 13     |
| `test_key_router.py`         | Tier state + key routing (public BYOK / owner)                     | 12     |
| `test_step_6_5.py`           | **Phase 6 journey:** recruiter login + quota + BYOK                | 5      |
| `test_upload.py`             | File count/extension validation; CSV + XLSX parsing; anon gate     | 18     |
| `test_infer.py`              | Type inference; table name sanitisation; ERD dataclasses           | 21     |
| `test_erd_validate.py`       | `build_erd`; `pk_not_unique`; `fk_type_mismatch`; orphan rate      | 17     |
| `test_plausibility.py`       | Haiku plausibility (mocked); `apply_decisions` accept/decline      | 15     |
| `test_step_7_5.py`           | Uploaded data queryable with JOIN; toggle absent without sign-off   | 2      |
| `test_phase_7_completion.py` | **Phase 7 journey:** upload → ERD → sign-off → cross-table JOIN    | 1      |
| `test_pii_scan.py`           | Deterministic PII detection per type; clean passes; no API         | 21     |
| `test_mask.py`               | One-way letters-only masking; nulls preserved; re-scan finds none  | 10     |
| `test_pii_classify.py`       | Ambiguous-column Haiku escalation (mocked); minimal sample; no-op  | 9      |
| `test_consent.py`            | Town/Postcode consent record + withdrawal + isolation              | 10     |
| `test_audit.py`              | Detection/resolution log (value-free) + subject filter             | 5      |
| `test_step_8_2.py`           | **8.2 journey:** PII block -> mask; clean passes                   | 2      |
| `test_step_8_5.py`           | **8.5 journey:** ToS gate blocks upload; privacy notice; caching   | 2      |
| `test_step_8_phase.py`       | **Phase 8 journey:** ToS -> PII block -> consent -> mask -> audit  | 1      |
| `test_step_9_0.py`           | Asset files, config.toml theme keys, logo SVG valid, app starts    | 8      |
| `test_step_9_1.py`           | About page: title, clean-room, /dev, GitHub link, Privacy Notice   | 6      |
| `test_step_9_2.py`           | How-it-works: 5 step headings, caching expander, data expander     | 5      |
| `test_step_9_3.py`           | README sections + privacy link; AI_CONTEXT Phase 9 modules         | 18     |
| `test_step_9_4.py`           | Secrets example, DEPLOY.md, bootstrap fn, app without owner key    | 10     |
| `test_phase_9_completion.py` | **Phase 9 journey:** themed app + About + How-it-works + README    | 4      |

The `test_step_*` and `test_phase_*_completion.py` files are the
**phase-completion (user-journey) tests** — the durable regression artefacts.
Run them after any change to confirm the app still works end to end.

---

## 8. Operational tasks

All commands run from the project root with the venv active
(`.venv\Scripts\activate`).

| Task                                                       | Command                                                                                                                                        |
|------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| Run the app                                                | `streamlit run app.py`                                                                                                                         |
| Run all tests                                              | `python -m pytest`                                                                                                                             |
| Run one test file                                          | `python -m pytest tests/test_step_5_6.py -v`                                                                                                   |
| Run the real-embedder test (downloads model, no API spend) | `RUN_MODEL_TESTS=1 python -m pytest tests/test_semantic.py -k Real`                                                                            |
| Inspect the cache                                          | `sqlite3 cache/cache.db "SELECT id, dataset_id, scope, question FROM templates;"`                                                              |
| Clear the cache                                            | delete `cache/cache.db` (it's rebuilt empty on next run; gitignored)                                                                           |
| Regenerate demo data                                       | `python data/prepare.py` (idempotent; fixed seed)                                                                                              |
| Inspect recruiter tokens                                   | `sqlite3 cache/auth.db "SELECT id, label, expires_at, queries_used, query_cap, active FROM recruiter_tokens;"`                                 |
| Mint a recruiter token (prints plaintext once)             | `python -c "from data_compass.auth import store, recruiter as r; c=store.connect('cache/auth.db'); print(r.create_recruiter_token(c,'Acme'))"` |
| Reset auth (re-seed admin from env)                        | delete `cache/auth.db`, set `ADMIN_PASSWORD`, restart                                                                                          |

**Where state lives:**
- BYOK API key → `st.session_state` only (never written to disk).
- Cache templates → `cache/cache.db` (SQLite; gitignored via `*.db` + `cache/`).
- Demo data → `data/land_registry/*.csv`, `data/weather/*.csv` (committed).

---

## 9. Configuration reference

Defined in [config.py](../src/data_compass/config.py); most are overridable via
environment variables (read at import, after `.env` is loaded).

| Setting               | Env var                       | Default             | Meaning                                  |
|-----------------------|-------------------------------|---------------------|------------------------------------------|
| Generation model      | —                             | `claude-sonnet-4-6` | Tier 4 SQL author                        |
| Cheap model           | —                             | `claude-haiku-4-5`  | Tier 3 adjudication + summaries          |
| Per-MTok rates        | —                             | see `MODEL_RATES`   | USD input/output prices                  |
| Cache-read multiplier | —                             | `0.1`               | Cache-read tokens billed at 10% of input |
| FX rate               | `FX_USD_TO_GBP`               | `0.79`              | USD→GBP, applied at display only         |
| Cache confidence      | `CACHE_THRESHOLD`             | `0.8`               | Min Haiku confidence for a Tier-3 hit    |
| FAISS candidates      | `CACHE_TOP_K`                 | `3`                 | Templates retrieved before adjudication  |
| Embedding model       | `EMBEDDING_MODEL`             | `all-MiniLM-L6-v2`  | Local sentence-transformers model        |
| Cache DB path         | —                             | `cache/cache.db`    | SQLite template store                    |
| Owner API key         | `ANTHROPIC_API_KEY`           | —                   | Admin/recruiter tier key (never public)  |
| Admin seed password   | `ADMIN_PASSWORD`              | —                   | Seeds admin on first run; blank = none   |
| Admin username        | `ADMIN_USERNAME`              | `admin`             | Admin login name                         |
| Admin renewal age     | `ADMIN_PASSWORD_MAX_AGE_DAYS` | `30`                | Days before admin password renewal       |
| Recruiter query cap   | `RECRUITER_QUERY_CAP`         | `20`                | Max queries per recruiter token          |
| Recruiter validity    | `RECRUITER_VALIDITY_DAYS`     | `30`                | Recruiter token lifetime (days)          |
| Auth DB path          | —                             | `cache/auth.db`     | SQLite users + recruiter tokens          |

---

## 10. Conventions & invariants

Hold these true in every change; the tests enforce most of them.

1. **British English** everywhere — UI, docs, comments.
2. **No hard-coded UI text.** Every user-facing string goes through `t()` and
   lives in `locales/en-GB.json`. Missing keys render `[missing: key]`, never crash.
3. **All tests mock the Claude API.** No live, billed calls in the suite.
4. **SQL is read-only.** Everything passes `is_safe_sql` before execution; the
   cache only stores SQL that executed cleanly.
5. **Money is computed in USD, displayed in GBP.** FX is applied at the UI edge only.
6. **The pipeline never raises.** `run_query` always returns a `QueryResult`;
   failures live in `.error`.
7. **Only the UI layer imports `streamlit`.** Keep core/building blocks pure.
8. **The API key is session-only.** Never persist it to disk or logs.
9. **The owner key never reaches a public visitor.** Only admin/recruiter tiers
   resolve to it; the recruiter gate runs *before* any API call.
10. **Secrets are hashed, never stored in clear.** Argon2id for admin passwords
    and recruiter tokens; a token's plaintext is shown once at creation.
11. **The LLM is untrusted; the SQL guard is the boundary.** Re-validate every
    model-produced SQL with `is_safe_sql`; never rely on prompt wording for safety.

---

## 11. "Where do I change…?" cookbook

| I want to…                  | Change this                                                            |
|-----------------------------|------------------------------------------------------------------------|
| Add a UI string             | `locales/en-GB.json`, then reference via `t("...")`                    |
| Add a demo dataset          | bundle files, register in `data/registry.py`, extend `data/prepare.py` |
| Tune cache aggressiveness   | `CACHE_THRESHOLD` / `CACHE_TOP_K` (env or `config.py`)                 |
| Change a model or its price | `MODEL_*` / `MODEL_RATES` in `config.py` (cost accounting picks it up) |
| Add a chart type            | `viz/autochart.py` `pick_chart()` + a `test_autochart.py` case         |
| Change SQL safety rules     | `sql/guard.py` block list / checks + `test_guard.py`                   |
| Adjust the summary style    | `_SYSTEM` prompt in `llm/summary.py`                                   |
| Add a new screen            | new file in `ui/`, import + route in `app.py`, add locale key          |
| Change the theme colours    | `.streamlit/config.toml` (primaryColor, backgroundColor, etc.)         |
| Replace the logo SVG        | `src/data_compass/assets/logo.svg` + `logo_icon.svg`                   |
| Add/replace the hero image  | drop `src/data_compass/assets/hero.png`; landing.py prefers it         |
| Add a new locale            | `locales/<tag>.json` mirroring `en-GB.json`; pass tag to `t()`         |
| Change tier→key routing     | `resolve_api_key` in `auth/key_router.py` + `test_key_router.py`       |
| Change recruiter limits     | `RECRUITER_QUERY_CAP` / `RECRUITER_VALIDITY_DAYS` (env or `config.py`) |
| Change the recruiter gate   | `check_access` in `auth/recruiter.py` + `test_recruiter.py`            |
| Adjust login UI / flow      | `ui/auth.py` (callbacks) + locale `auth.*` + `test_step_6_5.py`        |
