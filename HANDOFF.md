# Data Compass — Build Handoff

This project's specification and phased plan are complete and signed off. This
file is the instruction set for the session that will **implement** the plan.

## How to start (working directory matters)
Start the implementing session with its working directory set to **this
folder**:

```
c:\Users\giaco\OneDrive\Documenti\Git-Projects\Data Compass\
```

(or `cd` into it first). This is essential: the `/dev` workflow resumes from
`PLAN.md` **only when invoked from the directory that contains it**. Run it
elsewhere and it will try to start a brand-new project instead of resuming this
one.

## Prompt for the implementing session

```
We're building "Data Compass", a publicly-deployed natural-language → SQL
analytics web app (a portfolio piece). The full spec and phased plan already
exist in this project directory:

  - BRIEF.md — rationalised brief (features, auth tiers, tiered cache,
    ERD onboarding, PII failsafe, synthetic-data-only GDPR stance,
    cost transparency, About/How-it-works sections)
  - PLAN.md  — 9-phase development plan with microsteps, unit-test
    criteria, and user-journey phase-completion tests

Please run `/dev` (no arguments) from this directory to resume and implement
the plan. Read BRIEF.md and PLAN.md first, then build phase by phase following
the /dev workflow: one microstep at a time, write each microstep's unit test,
run it, then the user-journey phase-completion test, then the regression check
and living-docs update at each phase boundary. Pause at each phase boundary
for my review.

Standing rules (also recorded in PLAN.md):
- British English throughout; all user-facing strings externalised to the
  en-GB locale files from Phase 1.
- ALL tests must MOCK the Claude API — do NOT make any live, billed API calls
  during development without my explicit approval.
- Decide conventional/low-stakes choices yourself (note them as defaults);
  STOP and check with me for anything that changes scope or cost, has a
  legal/GDPR implication, hits the dataset-licence gate (Phase 2.1), or is
  hard to reverse / outward-facing (deployment, publishing, real spend).
- Do not deploy or push anything to a public host — that's an owner-performed
  step (Phase 9.4).

Start with Phase 1 (Scaffold & Shell).
```

## Expected early checkpoints
- **Phase 2.1 — dataset-licence gate.** The session must confirm the
  e-commerce and sports demo datasets are licensed for redistribution before
  bundling, and surface this for owner approval.
- **Phase 3** is the first phase that touches the Claude API (mocked in tests).
- **Phase 9.4** deployment + any real/billed API spend are owner-performed.
