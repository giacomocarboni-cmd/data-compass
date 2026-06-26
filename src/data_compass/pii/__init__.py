"""Personal-data (PII) detection and masking — Phase 8.

The deterministic scanner (:mod:`data_compass.pii.scan`) runs entirely
locally with no API calls and is the first line of the PII failsafe: it
detects emails, UK postcodes, UK phone numbers, National Insurance numbers,
payment-card numbers (Luhn-validated) and date-of-birth columns before any
uploaded data reaches storage, a prompt or the cache.
"""
