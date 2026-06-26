# Data Compass — Deployment Guide

> **This step is owner-performed.** Claude Code produces the configuration; the owner executes the deploy, supplies real API keys, and reviews legal text.

---

## Pre-deploy checklist

Before making the app public, complete all of the following:

- [ ] **Legal review** — `docs/PRIVACY_NOTICE.md` and the `legal.*` locale strings are marked **DRAFT**. Have them reviewed by a qualified professional before accepting real users.
- [ ] **GitHub repo URL** — update `about.repo_url` in `locales/en-GB.json` to the real repository URL.
- [ ] **Admin password** — set a strong value for `ADMIN_PASSWORD` in secrets; change it immediately after the first login.
- [ ] **Anthropic API key** — confirm the key is active and has sufficient quota for recruiter usage.
- [ ] **Hero image** — optionally drop `src/data_compass/assets/hero.png` (AI-generated) to replace the SVG placeholder.

---

## Streamlit Community Cloud deployment

### 1. Push the repository to GitHub

```bash
git remote add origin https://github.com/<your-username>/data-compass
git push -u origin main
```

### 2. Create a Streamlit Community Cloud account

Sign up at [share.streamlit.io](https://share.streamlit.io) with your GitHub account.

### 3. Create a new app

In the Streamlit Cloud dashboard:

1. Click **New app**.
2. Select your GitHub repository.
3. Set **Branch** to `main`.
4. Set **Main file path** to `app.py`.
5. Click **Advanced settings** and set **Python version** to **3.12** (or 3.11+).

### 4. Configure secrets

In the app settings, open the **Secrets** tab and paste the contents of `.streamlit/secrets.toml.example`, replacing the placeholder values with real ones:

```toml
ANTHROPIC_API_KEY = "sk-ant-api03-your-real-key"
ADMIN_PASSWORD = "a-strong-password"
```

Save the secrets. The app will restart automatically.

### 5. Deploy

Click **Deploy**. Streamlit Cloud installs dependencies from `pyproject.toml` and starts the app. The first cold start may take 2–5 minutes while sentence-transformers and FAISS download their models.

### 6. After the first deploy

1. Navigate to the **Account** tab and sign in as admin using the seeded credentials.
2. **Change the admin password immediately** via the Account panel.
3. Create recruiter tokens as needed.
4. Verify the app is working end-to-end with a test query.
5. Update `about.repo_url` in `locales/en-GB.json` to point to your live repository.
6. Update the live demo URL in `docs/README.md`.

---

## Local testing with secrets

Copy the example secrets file and fill in your values:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml
```

`.streamlit/secrets.toml` is in `.gitignore` — it will not be committed.

Run locally:

```bash
streamlit run app.py
```

---

## Dependency pinning

Dependencies are declared in `pyproject.toml` with minimum-version constraints. Streamlit Cloud installs from `pyproject.toml` directly. If you prefer a pinned `requirements.txt` for reproducible builds, generate one from a clean venv:

```bash
pip install -e .
pip freeze > requirements.txt
```

Commit `requirements.txt` alongside `pyproject.toml`. Streamlit Cloud will prefer `requirements.txt` if both are present.

---

## Hugging Face Spaces (fallback)

If Streamlit Community Cloud is unavailable:

1. Create a Space at [huggingface.co/spaces](https://huggingface.co/spaces), type **Streamlit**.
2. Push the repository to the Space's Git remote.
3. Set secrets via the Space settings → **Repository secrets**.
4. Set the app file to `app.py`.

---

## Notes on cost

- **Public visitors** use their own Anthropic API key (BYOK). No cost to the owner for public queries.
- **Admin / recruiter queries** use the `ANTHROPIC_API_KEY` secret. Recruiter tokens are capped at `RECRUITER_QUERY_CAP` queries (default 20) per token.
- The four-tier semantic cache minimises repeat costs — near-identical questions are often served from cache at zero or reduced API cost.
- A **caching warning** is shown to all users on the Query tab.
