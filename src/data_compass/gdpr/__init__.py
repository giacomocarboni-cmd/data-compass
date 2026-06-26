"""
GDPR accountability surfaces — Phase 8.

* :mod:`data_compass.gdpr.consent` — durable, per-user consent to *retain*
  Town/Postcode in uploaded data (otherwise masked by the PII failsafe), with
  withdrawal support.
* :mod:`data_compass.gdpr.audit` — an append-only log of PII detections and how
  they were resolved.

Consent is scoped to uploaded data only; the bundled demo datasets are OGL
public data (HM Land Registry, Met Office) about properties/places, not living
individuals, and need no consent.
"""
