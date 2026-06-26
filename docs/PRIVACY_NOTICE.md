# Data Compass — Privacy Notice

> **DRAFT — provided for demonstration purposes only. This is not legal advice.
> It must be reviewed (ideally by a qualified person) before the application is
> deployed publicly.**

_Last updated: 2026-06-22_

## 1. Who is responsible for your data

Data Compass is a personal portfolio demonstration application. The data
controller is **Giacomo Carboni**. For any privacy question, or to exercise your
data-protection rights, contact: **giacomo.carboni@gmail.com**.

## 2. What this app is for

Data Compass lets you ask questions in plain English about a dataset and returns
read-only SQL, a result table, a chart and a short summary. It is a
demonstration; it is **not** intended to process real personal data.

## 3. Please do not upload real personal data

By uploading data you confirm (see the Terms of Use shown before upload) that it
contains **no real personal data about identifiable living individuals**, or that
you have a lawful basis and all necessary consents to upload and process it.

The app includes an automatic failsafe that scans uploads for common personal
data (emails, UK postcodes, UK phone numbers, National Insurance numbers, payment
cards, dates of birth). When it finds such data it **pauses the upload, reports
what it found, and masks those values before anything is stored, queried or sent
to the AI model.** Masking is irreversible.

## 4. Town/Postcode retention (opt-in)

UK postcodes and Town/Postcode columns are masked by default. A logged-in user
may **opt in to retain** them for geographic analysis. This consent is recorded,
and may be **withdrawn at any time**; on withdrawal the retained values are
re-masked, any derived cached results are dropped, and the withdrawal is logged.

## 5. AI sub-processor

To generate SQL and summaries, the app sends your question, the dataset schema
(table and column names) and small samples of result data to **Anthropic, PBC**,
which acts as a **sub-processor**. Personal data detected by the failsafe is
masked before any such call. Do not send confidential information.

## 6. Caching

To keep costs low, your questions, the generated SQL templates and short result
summaries **may be cached and reused across sessions**, including between
different visitors of the same public demo dataset. Do not enter confidential
information into a query.

## 7. Bring-your-own-key (public visitors)

Public visitors supply their own Anthropic API key. It is held **in session
memory only**, never written to disk or logs, and is discarded when your session
ends.

## 8. Retention

Demo data is bundled and public (Open Government Licence). Uploaded data and its
DuckDB tables exist only for your session. Cached query templates/summaries and
the PII audit log persist to support the demonstration; they contain no raw
personal values.

## 9. Your rights

Under UK GDPR you have rights of access, rectification, erasure, restriction and
objection. Contact the controller above to exercise them. If you are not
satisfied, you may complain to the Information Commissioner's Office (ICO) at
**ico.org.uk**.
