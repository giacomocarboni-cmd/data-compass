"""Unit tests for the central config module."""

import os
import importlib


def test_model_rates_keys_present():
    from data_compass import config
    assert "claude-haiku-4-5" in config.MODEL_RATES
    assert "claude-sonnet-4-6" in config.MODEL_RATES
    assert "claude-opus-4-8" in config.MODEL_RATES


def test_haiku_rates_structure():
    from data_compass import config
    rates = config.MODEL_RATES["claude-haiku-4-5"]
    assert "input" in rates and "output" in rates
    assert isinstance(rates["input"], float)
    assert isinstance(rates["output"], float)


def test_cache_read_multiplier():
    from data_compass import config
    assert config.CACHE_READ_MULTIPLIER == 0.1


def test_env_override_cache_threshold(monkeypatch):
    """An env var override must change CACHE_THRESHOLD when the module reloads."""
    monkeypatch.setenv("CACHE_THRESHOLD", "0.65")
    import data_compass.config as cfg
    importlib.reload(cfg)
    assert cfg.CACHE_THRESHOLD == 0.65
    # Restore by reloading without the override
    monkeypatch.delenv("CACHE_THRESHOLD", raising=False)
    importlib.reload(cfg)


def test_default_cache_threshold():
    from data_compass import config
    importlib.reload(config)
    assert config.CACHE_THRESHOLD == 0.8
