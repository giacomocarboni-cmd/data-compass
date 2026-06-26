# Data Compass — Data Licences

All bundled demo datasets use Crown Copyright material licensed under the
[Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

---

## 1. UK Property Sales 2024 (`land_registry/`)

**Source:** HM Land Registry Price Paid Data
**URL:** <https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads>
**Coverage:** England and Wales, January–December 2024 (stratified subset, ~4,700 transactions)
**Files:**
- `land_registry/transactions.csv` — one row per registered sale (transaction UID, price, date, property ID, PPD category)
- `land_registry/properties.csv` — unique properties (postcode, type, tenure, address components, county)

**Licence notice (required by OGL v3):**
> Contains HM Land Registry data © Crown copyright and database right 2024.
> This data is licensed under the Open Government Licence v3.0.

**Permitted uses under OGL v3:** copy, publish, distribute, transmit, adapt, exploit commercially and non-commercially; attribution required.

**Personal data:** none. The Price Paid dataset records property transactions; it does not name buyers, sellers, or any individual. It is not subject to UK GDPR as personal data.

**Schema:**
| Table | Key columns |
|---|---|
| `transactions` | `transaction_uid` (PK), `property_id` (FK → `properties`), `price`, `transfer_date`, `ppd_category` |
| `properties` | `property_id` (PK), `postcode`, `property_type`, `old_new`, `duration`, `paon`, `saon`, `street`, `locality`, `town`, `district`, `county` |

---

## 2. UK Weather Stations 1990–2026 (`weather/`)

**Source:** Met Office Historic Station Data
**URL:** <https://www.metoffice.gov.uk/research/climate/maps-and-data/historic-station-data>
**Coverage:** 18 UK stations, monthly observations 1990 onwards
**Files:**
- `weather/stations.csv` — 18 stations with name, lat/lon, elevation, country, region
- `weather/observations.csv` — monthly readings per station (tmax, tmin, air frost days, rainfall, sunshine hours)

**Licence notice (required by OGL v3):**
> Contains public sector information licensed under the Open Government Licence v3.0.
> Source: Met Office Historic Station Data © Crown copyright 2024.

**Permitted uses under OGL v3:** same as above; attribution required.

**Personal data:** none. Meteorological measurements; no individuals involved.

**Schema:**
| Table | Key columns |
|---|---|
| `stations` | `station_id` (PK), `name`, `latitude`, `longitude`, `elevation_m`, `country`, `region` |
| `observations` | `obs_id` (PK), `station_id` (FK → `stations`), `year`, `month`, `tmax_c`, `tmin_c`, `af_days`, `rain_mm`, `sun_hours` |

**Stations included:**
Armagh · Bradford · Camborne · Cambridge · Chivenor · Durham · Eastbourne · Heathrow ·
Hurn · Lerwick · Leuchars · Lowestoft · Manston · Nairn · Oxford · Stornoway · Tiree · Valley

---

## Preparing / refreshing the data

The script `data/prepare.py` downloads and reshapes both datasets from their official sources.
Run it from the project root when you need to refresh:

```bash
python data/prepare.py
```

The script is idempotent and reproducible (fixed random seed).
