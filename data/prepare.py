#!/usr/bin/env python3
"""
Data preparation script for Data Compass demo datasets.
Downloads and shapes:
  1. HM Land Registry Price Paid Data (2024 Part 1) — Crown Copyright, OGL v3
  2. Met Office Historic Station Data (selected UK stations) — Crown Copyright, OGL v3

Run from the project root:
    python data/prepare.py

Outputs:
    data/land_registry/transactions.csv
    data/land_registry/properties.csv
    data/weather/stations.csv
    data/weather/observations.csv
"""
import csv
import hashlib
import io
import re
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).parent
LAND_DIR = ROOT / "land_registry"
WEATHER_DIR = ROOT / "weather"

# ── Land Registry ─────────────────────────────────────────────────────────────

LR_URL = (
    "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com"
    "/pp-2024-part1.csv"
)
LR_COLUMNS = [
    "transaction_uid", "price", "transfer_date", "postcode",
    "property_type", "old_new", "duration",
    "paon", "saon", "street", "locality", "town", "district", "county",
    "ppd_category", "record_status",
]
PROPERTY_TYPE_MAP = {
    "D": "Detached", "S": "Semi-detached",
    "T": "Terraced", "F": "Flat", "O": "Other",
}
DURATION_MAP = {"F": "Freehold", "L": "Leasehold"}
OLD_NEW_MAP   = {"Y": "New build", "N": "Established"}
TARGET_TXN    = 6_000   # target transaction rows in the final CSV
OVERSAMPLE    = 5       # read this many × target before filtering


def _property_id(row: dict) -> str:
    key = "|".join([row["postcode"], row["paon"], row["saon"], row["street"], row["locality"]])
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def prepare_land_registry() -> None:
    print("Land Registry: streaming 2024 Part 1 ...")
    LAND_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    limit = TARGET_TXN * OVERSAMPLE
    with requests.get(LR_URL, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        reader = csv.reader(
            io.TextIOWrapper(resp.raw, encoding="latin-1", errors="replace")
        )
        for line in reader:
            if len(line) != 16:
                continue
            row = dict(zip(LR_COLUMNS, line))
            if row["record_status"] != "A":
                continue
            rows.append(row)
            if len(rows) >= limit:
                break

    print(f"  Read {len(rows):,} raw rows")
    df = pd.DataFrame(rows)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["price", "postcode"])
    df["transfer_date"] = (
        pd.to_datetime(df["transfer_date"], errors="coerce")
        .dt.date.astype(str)
    )

    # Stratified sample: spread evenly across counties
    # (explicit concat avoids pandas 3.0 groupby.apply column-exclusion behaviour)
    n_counties = df["county"].nunique()
    per_county = max(1, TARGET_TXN // n_counties)
    parts = [
        g.sample(min(len(g), per_county), random_state=42)
        for _, g in df.groupby("county")
    ]
    sampled = pd.concat(parts).head(TARGET_TXN).copy()

    sampled["property_id"]    = sampled.apply(_property_id, axis=1)
    sampled["property_type"]  = sampled["property_type"].map(PROPERTY_TYPE_MAP).fillna("Other")
    sampled["duration"]       = sampled["duration"].map(DURATION_MAP).fillna(sampled["duration"])
    sampled["old_new"]        = sampled["old_new"].map(OLD_NEW_MAP).fillna(sampled["old_new"])

    txn = sampled[["transaction_uid", "property_id", "price", "transfer_date", "ppd_category"]]
    txn.to_csv(LAND_DIR / "transactions.csv", index=False)
    print(f"  transactions.csv  — {len(txn):,} rows")

    props = (
        sampled.drop_duplicates("property_id")[
            ["property_id", "postcode", "property_type", "old_new", "duration",
             "paon", "saon", "street", "locality", "town", "district", "county"]
        ]
    )
    props.to_csv(LAND_DIR / "properties.csv", index=False)
    print(f"  properties.csv    — {len(props):,} rows")


# ── Met Office Historic Station Data ──────────────────────────────────────────

STATIONS = [
    # slug,          display name,     lat,     lon,   elev_m, country,           region
    ("heathrow",     "Heathrow",     51.479, -0.449,    25, "England",           "Greater London"),
    ("oxford",       "Oxford",       51.761, -1.262,    63, "England",           "Oxfordshire"),
    ("cambridge",    "Cambridge",    52.200,  0.117,    12, "England",           "Cambridgeshire"),
    ("lowestoft",    "Lowestoft",    52.476,  1.731,    25, "England",           "Suffolk"),
    ("manston",      "Manston",      51.347,  1.341,    50, "England",           "Kent"),
    ("hurn",         "Hurn",         50.779, -1.832,    10, "England",           "Dorset"),
    ("camborne",     "Camborne",     50.218, -5.327,    87, "England",           "Cornwall"),
    ("chivenor",     "Chivenor",     51.087, -4.150,     8, "England",           "Devon"),
    ("bradford",     "Bradford",     53.810, -1.770,   133, "England",           "West Yorkshire"),
    ("durham",       "Durham",       54.767, -1.583,    69, "England",           "County Durham"),
    ("valley",       "Valley",       53.252, -4.534,    10, "Wales",             "Anglesey"),
    ("armagh",       "Armagh",       54.352, -6.649,    62, "Northern Ireland",  "Armagh"),
    ("lerwick",      "Lerwick",      60.139, -1.185,    82, "Scotland",          "Shetland"),
    ("tiree",        "Tiree",        56.499, -6.879,     9, "Scotland",          "Argyll and Bute"),
    ("nairn",        "Nairn",        57.593, -3.897,     7, "Scotland",          "Highland"),
    ("leuchars",     "Leuchars",     56.377, -2.863,    10, "Scotland",          "Fife"),
    ("stornoway",    "Stornoway",    58.213, -6.317,    15, "Scotland",          "Western Isles"),
    ("eastbourne",   "Eastbourne",   50.757,  0.273,    40, "England",           "East Sussex"),
]

MET_BASE   = "https://www.metoffice.gov.uk/pub/data/weather/uk/climate/stationdata/{slug}data.txt"
YEAR_START = 1990


def _parse_station_text(text: str, slug: str) -> list[dict]:
    records: list[dict] = []
    in_data = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^yyyy\s+mm", line):
            in_data = True
            continue
        if re.match(r"^degC|^Provisional|^Site", line):
            continue
        if not in_data:
            continue
        clean = re.sub(r"[*#]", "", line)
        parts = clean.split()
        if len(parts) < 2:
            continue
        try:
            year  = int(parts[0])
            month = int(parts[1])
        except ValueError:
            continue
        if year < YEAR_START:
            continue

        def _f(idx: int) -> float | None:
            if idx >= len(parts):
                return None
            v = parts[idx]
            if v in ("---", "-"):
                return None
            try:
                return float(v)
            except ValueError:
                return None

        records.append({
            "station_id": slug,
            "year":       year,
            "month":      month,
            "tmax_c":     _f(2),
            "tmin_c":     _f(3),
            "af_days":    _f(4),
            "rain_mm":    _f(5),
            "sun_hours":  _f(6),
        })
    return records


def prepare_weather() -> None:
    print("Met Office: downloading historic station data ...")
    WEATHER_DIR.mkdir(parents=True, exist_ok=True)

    station_rows: list[dict] = []
    obs_rows:     list[dict] = []
    failed:       list[str]  = []

    for slug, name, lat, lon, elev, country, region in STATIONS:
        url = MET_BASE.format(slug=slug)
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            records = _parse_station_text(resp.text, slug)
            if not records:
                print(f"  WARN  {name}: 0 records parsed -- skipping")
                failed.append(slug)
                continue
            station_rows.append({
                "station_id": slug, "name": name,
                "latitude": lat, "longitude": lon,
                "elevation_m": elev, "country": country, "region": region,
            })
            obs_rows.extend(records)
            print(f"  OK  {name}: {len(records)} observations")
        except Exception as exc:
            print(f"  FAIL  {name}: {exc}")
            failed.append(slug)

    if failed:
        print(f"  Stations skipped: {failed}")

    pd.DataFrame(station_rows).to_csv(WEATHER_DIR / "stations.csv", index=False)
    print(f"  stations.csv      — {len(station_rows)} stations")

    obs_df = pd.DataFrame(obs_rows)
    obs_df.insert(
        0, "obs_id",
        obs_df["station_id"] + "_"
        + obs_df["year"].astype(str) + "_"
        + obs_df["month"].astype(str).str.zfill(2),
    )
    obs_df.to_csv(WEATHER_DIR / "observations.csv", index=False)
    print(f"  observations.csv  — {len(obs_df):,} rows")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prepare_land_registry()
    print()
    prepare_weather()
    print("\nAll done.")
