"""Unit tests for Step 2.3 — Dataset picker & table browser UI."""
from streamlit.testing.v1 import AppTest


def _app() -> AppTest:
    return AppTest.from_file("app.py", default_timeout=30)


class TestDatasetPickerSidebar:
    def test_dataset_selectbox_present_in_sidebar(self):
        at = _app().run()
        labels = [sb.label for sb in at.selectbox]
        assert any("dataset" in label.lower() or "Demo" in label for label in labels)

    def test_default_state_shows_landing(self):
        at = _app().run()
        # With no dataset selected, landing title must be visible
        texts = " ".join(
            e.value for e in list(at.title) + list(at.markdown) + list(at.info)
        )
        assert "Data Compass" in texts

    def test_selecting_land_registry_renders_table_list(self):
        at = _app().run()
        picker = next(sb for sb in at.selectbox if "dataset" in sb.label.lower() or "Demo" in sb.label)
        at = picker.select("UK Property Sales 2024").run()

        # Main panel should have a header with the dataset name
        headers = " ".join(h.value for h in list(at.header) + list(at.subheader))
        assert "UK Property Sales 2024" in headers or "Property Sales" in headers

    def test_selecting_weather_renders_table_list(self):
        at = _app().run()
        picker = next(sb for sb in at.selectbox if "dataset" in sb.label.lower() or "Demo" in sb.label)
        at = picker.select("UK Weather Stations 1990–2026").run()

        headers = " ".join(h.value for h in list(at.header) + list(at.subheader))
        assert "Weather" in headers or "weather" in headers.lower()

    def test_land_registry_shows_both_table_expanders(self):
        at = _app().run()
        picker = next(sb for sb in at.selectbox if "dataset" in sb.label.lower() or "Demo" in sb.label)
        at = picker.select("UK Property Sales 2024").run()

        expander_labels = " ".join(str(e) for e in at.expander)
        assert "transactions" in expander_labels.lower()
        assert "properties" in expander_labels.lower()

    def test_weather_shows_both_table_expanders(self):
        at = _app().run()
        picker = next(sb for sb in at.selectbox if "dataset" in sb.label.lower() or "Demo" in sb.label)
        at = picker.select("UK Weather Stations 1990–2026").run()

        expander_labels = " ".join(str(e) for e in at.expander)
        assert "stations" in expander_labels.lower()
        assert "observations" in expander_labels.lower()

    def test_preview_dataframe_present_after_selection(self):
        at = _app().run()
        picker = next(sb for sb in at.selectbox if "dataset" in sb.label.lower() or "Demo" in sb.label)
        at = picker.select("UK Property Sales 2024").run()
        # At least one dataframe (the preview) must be rendered
        assert len(at.dataframe) >= 1
