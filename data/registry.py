"""
Registry of bundled demo datasets for Data Compass.

Each entry describes a dataset: its display name, the files that belong to it,
schema hints (primary / foreign keys), and a licence note required for attribution.

All datasets use Crown Copyright material licensed under the
Open Government Licence v3.0 — see docs/DATA_LICENCES.md.
"""
from __future__ import annotations

from pathlib import Path

_DATA_DIR = Path(__file__).parent


def _rel(*parts: str) -> str:
    """Return a path string relative to the data/ directory."""
    return str(_DATA_DIR.joinpath(*parts))


REGISTRY: list[dict] = [
    {
        "id": "land_registry",
        "name": "UK Property Sales 2024",
        "description": (
            "Sales transactions and property records from HM Land Registry "
            "Price Paid Data for England and Wales, January–December 2024. "
            "~4,700 transactions across all property types and counties."
        ),
        "tables": {
            "transactions": _rel("land_registry", "transactions.csv"),
            "properties":   _rel("land_registry", "properties.csv"),
        },
        "schema_hints": {
            "primary_keys": {
                "transactions": "transaction_uid",
                "properties":   "property_id",
            },
            "foreign_keys": [
                {
                    "from_table":  "transactions",
                    "from_column": "property_id",
                    "to_table":    "properties",
                    "to_column":   "property_id",
                }
            ],
        },
        "licence": (
            "Contains HM Land Registry data © Crown copyright and database right 2024. "
            "This data is licensed under the Open Government Licence v3.0. "
            "Source: HM Land Registry Price Paid Data, "
            "https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads"
        ),
        "licence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "source_url":  "https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads",
    },
    {
        "id": "uk_weather",
        "name": "UK Weather Stations 1990–2026",
        "description": (
            "Monthly climate observations from 18 long-running UK Met Office weather stations, "
            "covering England, Wales, Scotland and Northern Ireland. "
            "Variables: max/min temperature, air frost days, rainfall, sunshine hours."
        ),
        "tables": {
            "stations":     _rel("weather", "stations.csv"),
            "observations": _rel("weather", "observations.csv"),
        },
        "schema_hints": {
            "primary_keys": {
                "stations":     "station_id",
                "observations": "obs_id",
            },
            "foreign_keys": [
                {
                    "from_table":  "observations",
                    "from_column": "station_id",
                    "to_table":    "stations",
                    "to_column":   "station_id",
                }
            ],
        },
        "licence": (
            "Contains public sector information licensed under the "
            "Open Government Licence v3.0. "
            "Source: Met Office Historic Station Data, "
            "https://www.metoffice.gov.uk/research/climate/maps-and-data/historic-station-data"
        ),
        "licence_url": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "source_url":  "https://www.metoffice.gov.uk/research/climate/maps-and-data/historic-station-data",
    },
]


def get_dataset(dataset_id: str) -> dict:
    """Return the registry entry for a dataset by its id, or raise KeyError."""
    for entry in REGISTRY:
        if entry["id"] == dataset_id:
            return entry
    raise KeyError(f"Unknown dataset: {dataset_id!r}")
