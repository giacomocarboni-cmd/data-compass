# BRIEF — Data Compass

> **Tagline (short):** *Navigate your data without getting lost in deep analytical waters.*
>
> **Subtitle (README / landing):** *Ask questions in plain English and let Data Compass chart the route through your dataset — no SQL, no deep analytical waters.*
>
> A natural-language analytics assistant: ask a question in plain English, get back the SQL, a result table, an auto-chart, and a short summary. Built as a portfolio piece demonstrating a **Data Scientist who ships AI tooling** (NL→SQL, RAG, tiered LLM cost optimisation, GDPR-aware data handling).
>
> **Name chosen: Data Compass** (neutral; quietly echoes the owner's Kitchen Compass project, no employer-product resemblance). Clean-room build: no employer code, data, schemas, glossaries, or process reused.

---

## 1. Purpose & positioning

- **Primary goal:** a publicly deployed (web URL) artefact that closes the "desktop-only / no cloud deployment" gap on the CV and showcases the rare blend — quantitative analyst *and* LLM-application builder.
- **Showcases:** NL→SQL, local RAG (FAISS + sentence-transformers), a deliberate multi-tier LLM cost-optimisation strategy, data-quality/ERD onboarding, and privacy-by-design.
- **Audience:** hiring managers / recruiters for analytics × AI-engineering roles.

## 2. Goals / Non-goals

**Goals**
- Demonstrable, live, on a public URL.
- Cheap to run (tiered caching; deterministic-before-AI everywhere).
- Visibly safe and well-engineered (cost shown per action; GDPR posture explicit).

**Non-goals**
- Not a commercial product; not marketed; not pitched at any employer's market or clients.
- Not a general-purpose BI tool. Scope is deliberately small.
- **Never processes real personal data** (see §6).

## 3. Users & authentication

| Tier | Who | API key used | Limits |
|---|---|---|---|
| **Public** | Anyone | **Bring-your-own-key (BYOK)** — visitor pastes their own Anthropic key, held in session memory only, never persisted | None (they pay) |
| **Admin** | Owner | **Owner's key** | Login never expires; password force-renewed every 30 days |
| **Recruiter (temp)** | Shared on request | **Owner's key** | **20 queries OR 30 days, whichever first**; deactivates afterwards regardless of queries remaining |

Mechanics:
- Recruiter record: `created_at`, `expires_at = created_at + 30d`, `queries_used`, `queries_cap = 20`, `active`. Gate each request on `active AND now < expires_at AND queries_used < 20`. Checked **lazily** at login/query time — no cron.
- Admin: store `password_set_at`; force change when `now > set_at + 30d`. Username never expires.
- Passwords hashed (bcrypt/argon2); recruiter tokens random and stored hashed. No plaintext secrets.

## 4. Core features

### 4.1 NL→SQL query engine
- Question → SQL → execute in **DuckDB** (in-process; no DB server) → return **result table + auto-chart (Plotly/Altair) + one-paragraph summary**.
- **Always display the generated SQL** (transparency + guard against silent wrong answers).
- Read-only SQL only; validate before execution.

### 4.2 Dataset onboarding (ERD with sign-off)
- Upload **up to 3 files** for one dataset (logged-in users only — see §6).
- User declares **PK/FK relationships** between files.
- **Zero-API ERD** built from declared keys + locally-inferred column types/headers (pandas).
- **Deterministic validation first (free):** PK uniqueness, FK↔PK type compatibility, orphan rates. Catches most real errors at no cost.
- **Haiku only for semantic plausibility** (judgment calls deterministic checks can't make, e.g. a join that is type-valid but semantically wrong).
- **Non-destructive sign-off:** each proposed correction shown as *"I changed X→Y because [reason]. Confirm, or keep your original?"* — **default to the user's original** if not confirmed. (Mirrors a formal data-onboarding sign-off.)
- Verified ERD is injected into the SQL-generation prompt as the join map.

### 4.3 Tiered semantic cache (the cost-optimisation core)
Cheapest-first pipeline:
1. **Exact / normalised match — free.** Normalise question; direct lookup. Identical repeats cost **zero API calls**.
2. **Semantic retrieval — free, local (RAG).** Embed question with **sentence-transformers**; retrieve top-K similar templates from **FAISS**. Narrows thousands of templates to ~3 candidates at no cost.
3. **Haiku adjudication + parameter extraction — cheap.** Haiku decides if any candidate truly matches the *intent* and extracts parameters (time window, category, threshold) to slot into the template's WHERE clause. Handles *"revenue last month"* vs *"revenue last year"* = **same template, different params**.
4. **Miss → Sonnet generation — the expensive path.** Sonnet writes SQL **as a parameterised template** (placeholders + param definitions), which is embedded and stored for reuse — **only if it produced valid, executable SQL**.

Guards:
- **Confidence-gated reuse** — Haiku returns a confidence; reuse only above threshold (false matches are worse than misses).
- **SQL always shown** to the user, so a wrong match is visible.
- Cache stores **SQL templates, not results** (data may change; re-run each time).

Economics (be honest in the UI copy): a cache *hit* still costs ~1 Haiku call; caching saves the *Sonnet* call (the expensive ~90%). Tier 1 (exact match) costs nothing — so the app gets cheaper per query with use. This is a real, named technique (**semantic caching + query templating**), fair to present as deliberate cost engineering.

### 4.4 Cost & model transparency
- After **every upload** and **every query**, show **models used + total cost**, computed from the API response `usage` (input / output / cache-read tokens × current rates).
- **Pure cache hit → "No AI used · £0.00".**
- Per-token rates live in **one config constant** (re-checkable against the Models API).

### 4.5 "About / How this was made" page (in-app)
A short, honest in-app section — deliberate portfolio meta-story:
- States it was **clean-room built as a portfolio piece** (no employer assets).
- Explains it was developed using a **custom Claude Code slash-command skill (`/dev`) the owner created himself** — phased development, microstep tests, regression checks, and living documentation. Notes that the skill's front-end is the owner's **Create Plan App** personal project (brief → BRIEF.md / PLAN.md).
- Names the stack honestly and links to the GitHub repo + privacy notice.
- Tasteful and factual — no overclaiming.

### 4.6 "How it works" — plain-English user docs (in-app)
A brief, non-technical explainer shown to users (short version, not a manual):
1. Pick a ready-made dataset (e-commerce or sports), or — if logged in — upload your own.
2. Ask a question in plain English.
3. Data Compass first checks whether it has answered something similar before (free); if not, it asks the AI to write the SQL for you.
4. You get the SQL it used, a table, a chart, and a short summary.
5. It shows which AI models ran and what it cost — or "No AI used · £0.00" when the answer came from cache.
- Plus a one-line note: questions may be cached to speed things up, and the app uses synthetic data only.

## 5. Data policy — SYNTHETIC DATA ONLY (compliance spine)

**The app must never ingest real personal data.** This is the single decision that keeps the project out of most of UK GDPR's scope (UK GDPR does not apply to data that is not personal data).

- **Public demo** runs on **two bundled public datasets the user chooses between — open e-commerce and sports** (no real individuals). Neutral domains — deliberately NOT retail-loyalty or charity (avoids any employer-product resemblance). Two datasets also demonstrates the schema-aware ERD/SQL working across different shapes.
- **Upload (logged-in only)** is gated by a **Terms-of-Use acceptance** in which the uploader **warrants the file contains no real personal data** (synthetic or fully de-identified) and that they have the right to upload it.
- **Masking is a *demonstrated feature*, not a compliance crutch:** on ingest, detect likely PII (deterministic heuristics — column-name + UK-postcode/email regex — then Haiku only for ambiguous columns), **mask by default before any storage or API call**, and **show the user what was masked**. Town/Postcode retained only on **explicit opt-in**.
- **Mask before any API call** — raw values for masked columns must never be sent to Anthropic. The model and the cache only ever see the masked version.
- **Cache scope:** uploaded data + its cache are **private to the uploading login and purged on login expiry**, unless explicit consent to retain. Shared cache is for the bundled synthetic dataset only.
- **Query-text PII:** warn that questions may be cached; the same masking principle applies — a name typed into a question is still PII.

### 5.1 Failsafe — if a user uploads personal data anyway
Defence-in-depth, deterministic-first, all **before any API call or persistence** (upload is logged-in only, so the uploader population is owner + vetted recruiters — small and known):
1. **Pre-ingest PII scan (local, free):** column-name heuristics + value regex (UK postcode, email, UK phone, NINO, card via Luhn, DOB).
2. **Block-and-warn, don't silently proceed:** on detection, stop and report exactly what was found; offer cancel or auto-mask. **Nothing is sent to Anthropic until the user resolves it.**
3. **Mask-before-API invariant:** if they proceed, raw PII columns are masked locally; the model and cache only ever see masked data.
4. **Ambiguous columns → Haiku** on minimal/sampled tokens only (never the full raw column); prefer the free deterministic checks.
5. **No raw persistence:** only the masked dataset is stored/cached; raw bytes discarded after masking; uploads purge on login expiry.
6. **Audit + sign-off record:** log that detection fired and how it was resolved (accountability trail).

**Residual (honest):** detection is imperfect (free-text columns can hide PII; special-category data is hard to pattern-match). Position = ToS breach by the uploader, caught-and-masked by the failsafe, minimised by logged-in-only access — **substantially contained, not zero risk**.

## 6. UK GDPR position (grounded in ICO guidance — see §10 sources)

**Stance:** by processing **synthetic data only**, there is no personal data, so the controller/processor obligations and international-transfer rules do not bite. The masking pipeline, consent prompts, privacy notice, and ToS are **defence-in-depth + portfolio signal**, not the thing the compliance rests on.

Still ship regardless (cheap, good signalling, and the backstop if someone uploads real data against the terms):
- **A privacy notice** (Right to be Informed): who the owner is, what is processed, why, retention, **Anthropic named as a sub-processor**, data-subject rights, ICO complaint route.
- **A Terms-of-Use upload gate**: no-real-personal-data warranty + right-to-upload warranty + indemnity (see §7).
- **Caching/privacy warning** shown up front to all tiers.

## 7. Can liability be pushed to the uploader? (answer baked into design)

Per ICO: a **controller is responsible regardless of the contract terms**, and a **processor carries direct statutory duties in its own right** (security, breach notification, accountability). So **you cannot contractually escape statutory liability to data subjects / the ICO** for real personal data you actually process — and using a processor (Anthropic) for real personal data would itself require a written Art 28 contract + a Transfer Risk Assessment + IDTA/Addendum for the transfer.

**Therefore the only robust "push" is to have nothing in scope:**
- **Technical:** synthetic-data-only; masking before storage/API; no persistence of uploads beyond the login.
- **Contractual (ToS):** uploader **warrants** the data is non-personal/synthetic and that they have the right to upload, and **indemnifies** the owner against breach of that warranty. This allocates liability *between the parties* and is a genuine deterrent — but it works precisely because, combined with the technical controls, **there should be no personal data for statutory liability to attach to.** The contract is the backstop for misuse, not a shield for processing real data.

## 8. Tech stack

| Layer | Choice |
|---|---|
| App / UI | Streamlit (Python-native, fast to a public URL) |
| LLM | Claude API via official Anthropic Python SDK — **Haiku 4.5** (match/adjudication, PII classification, ERD plausibility), **Sonnet 4.6** (SQL generation) |
| SQL engine | DuckDB (in-process) + pandas |
| RAG / cache retrieval | FAISS + sentence-transformers (local, zero-cost embeddings) |
| Charts | Plotly or Altair |
| Auth/store | SQLite (logins, recruiter quotas, cache templates + embeddings, consent records) |
| Hosting | Hugging Face Spaces or Streamlit Community Cloud (free, public URL) |
| Repo | GitHub — README with screenshots, architecture diagram, live link, privacy notice |

## 9. Cost model (current rates, per-MTok input/output)
- Haiku 4.5: $1 / $5 · Sonnet 4.6: $3 / $15 · Opus 4.8: $5 / $25.
- Cache hit ≈ 1 Haiku call (~$0.001). Cache miss ≈ Haiku + Sonnet (~$0.01). Exact-match tier = £0.
- Prompt-cache the stable schema/glossary/system prefix (cache reads ≈ 0.1× input price).
- Owner exposure bounded by: BYOK for public + a **Console monthly spend cap** on a **dedicated API key** for this project.

## 10. Compliance gap register (ICO-grounded) & status

| Gap (from earlier review) | Status under this brief |
|---|---|
| Masking ≠ anonymisation; postcode re-identifies (motivated-intruder test) | **Resolved** — synthetic data only; postcode retention is opt-in and only ever on synthetic data |
| Special category data (Art 9) | **Resolved** — no real data; synthetic dataset avoids special categories by construction |
| International transfer to Anthropic (IDTA/Addendum + TRA) | **Resolved** — no personal data transferred; document Anthropic as sub-processor anyway |
| Privacy notice (Arts 13–14) | **To build** — full notice incl. Anthropic sub-processor + ICO route |
| Consent (specific, withdrawable, recorded) | **To build** — opt-in for Town/Postcode + retention; store consent records; allow withdrawal |
| Controller/processor ambiguity | **Resolved** — no personal data ⇒ no relationship; ToS sets uploader as responsible party |
| PII via query text | **Mitigated** — caching warning + masking principle applies to questions |
| Imperfect PII detection | **Acceptable** — synthetic data only; detection is a demoed feature, not a safety guarantee |

## 11. Open decisions
- [x] **Confirmed: upload = logged-in only.** Public/BYOK uses the bundled synthetic dataset.
- [x] **Demo datasets chosen: open e-commerce + sports** (user picks one). Not retail-loyalty/charity.
- [x] **Name chosen: Data Compass.** Tagline: *"Navigate your data without getting lost in deep analytical waters."*
- [ ] BYOK vs login-gate as the default public experience.
- [ ] Whether to fetch live ICO wording for the privacy-notice text at build time.

## 12. Out of scope
- Real personal data of any kind.
- Write/UPDATE/DELETE SQL.
- Multi-tenant production hardening, SSO, billing.
- Anything referencing or resembling an employer product.
