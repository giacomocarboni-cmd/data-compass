"""Unit tests for Step 2.1 — Bundle demo datasets + registry (LICENCE GATE)."""
from pathlib import Path
import pytest
import sys

# Ensure data/ is importable from the project root
sys.path.insert(0, str(Path(__file__).parent.parent))
from data.registry import REGISTRY, get_dataset


class TestRegistry:
    def test_exactly_two_datasets(self):
        assert len(REGISTRY) == 2

    def test_required_fields_present(self):
        for entry in REGISTRY:
            for field in ("id", "name", "description", "tables", "schema_hints",
                          "licence", "licence_url", "source_url"):
                assert field in entry, f"Missing field {field!r} in dataset {entry.get('id')}"

    def test_licence_note_nonempty(self):
        for entry in REGISTRY:
            assert entry["licence"].strip(), f"Empty licence for {entry['id']}"
            assert "OGL" in entry["licence"] or "Open Government Licence" in entry["licence"], (
                f"Licence note for {entry['id']} does not mention OGL"
            )

    def test_all_data_files_exist(self):
        for entry in REGISTRY:
            for table_name, path in entry["tables"].items():
                p = Path(path)
                assert p.exists(), (
                    f"Missing file for {entry['id']}.{table_name}: {path}"
                )
                assert p.stat().st_size > 0, f"Empty file: {path}"

    def test_schema_hints_present(self):
        for entry in REGISTRY:
            hints = entry["schema_hints"]
            assert "primary_keys" in hints
            assert "foreign_keys" in hints
            for table in entry["tables"]:
                assert table in hints["primary_keys"], (
                    f"No primary key hint for table {table!r} in {entry['id']}"
                )

    def test_get_dataset_by_id(self):
        lr = get_dataset("land_registry")
        assert lr["id"] == "land_registry"
        wt = get_dataset("uk_weather")
        assert wt["id"] == "uk_weather"

    def test_get_dataset_unknown_raises(self):
        with pytest.raises(KeyError):
            get_dataset("does_not_exist")


class TestDataFileContents:
    """Smoke-check that the CSV files are well-formed and have expected columns."""

    def test_land_registry_transactions_columns(self):
        import pandas as pd
        df = pd.read_csv(get_dataset("land_registry")["tables"]["transactions"], nrows=5)
        expected = {"transaction_uid", "property_id", "price", "transfer_date", "ppd_category"}
        assert expected.issubset(set(df.columns))

    def test_land_registry_properties_columns(self):
        import pandas as pd
        df = pd.read_csv(get_dataset("land_registry")["tables"]["properties"], nrows=5)
        expected = {"property_id", "postcode", "property_type", "county"}
        assert expected.issubset(set(df.columns))

    def test_weather_stations_columns(self):
        import pandas as pd
        df = pd.read_csv(get_dataset("uk_weather")["tables"]["stations"], nrows=5)
        expected = {"station_id", "name", "latitude", "longitude", "country"}
        assert expected.issubset(set(df.columns))

    def test_weather_observations_columns(self):
        import pandas as pd
        df = pd.read_csv(get_dataset("uk_weather")["tables"]["observations"], nrows=5)
        expected = {"obs_id", "station_id", "year", "month", "tmax_c", "rain_mm"}
        assert expected.issubset(set(df.columns))

    def test_fk_consistency_land_registry(self):
        """Every transaction.property_id must exist in properties.property_id."""
        import pandas as pd
        entry = get_dataset("land_registry")
        txn   = pd.read_csv(entry["tables"]["transactions"])
        props = pd.read_csv(entry["tables"]["properties"])
        missing = set(txn["property_id"]) - set(props["property_id"])
        assert not missing, f"{len(missing)} transaction property_ids missing from properties table"

    def test_fk_consistency_weather(self):
        """Every observation.station_id must exist in stations.station_id."""
        import pandas as pd
        entry = get_dataset("uk_weather")
        obs      = pd.read_csv(entry["tables"]["observations"])
        stations = pd.read_csv(entry["tables"]["stations"])
        missing = set(obs["station_id"]) - set(stations["station_id"])
        assert not missing, f"{len(missing)} observation station_ids missing from stations table"
