"""Unit tests for z2g.config."""
import pytest

from z2g import config


def test_resolve_path_absolute(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    abs_path = tmp_path / "foo" / "bar"
    abs_path.mkdir(parents=True, exist_ok=True)
    assert config.resolve_path(str(abs_path)) == str(abs_path.resolve())


def test_resolve_path_relative(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    assert config.resolve_path("secrets/google_client_secret.json") == str((tmp_path / "secrets" / "google_client_secret.json").resolve())


def test_verbose_enabled_false(monkeypatch):
    monkeypatch.delenv("Z2G_VERBOSE", raising=False)
    assert config.verbose_enabled() is False
    monkeypatch.setenv("Z2G_VERBOSE", "0")
    assert config.verbose_enabled() is False
    monkeypatch.setenv("Z2G_VERBOSE", "false")
    assert config.verbose_enabled() is False


def test_verbose_enabled_true(monkeypatch):
    monkeypatch.setenv("Z2G_VERBOSE", "1")
    assert config.verbose_enabled() is True
    monkeypatch.setenv("Z2G_VERBOSE", "true")
    assert config.verbose_enabled() is True
    monkeypatch.setenv("Z2G_VERBOSE", "yes")
    assert config.verbose_enabled() is True


def test_env_present(monkeypatch):
    monkeypatch.setenv("TEST_VAR_XYZ", "value")
    assert config.env("TEST_VAR_XYZ") == "value"


def test_env_missing(monkeypatch):
    monkeypatch.delenv("MISSING_VAR_XYZ", raising=False)
    with pytest.raises(RuntimeError, match="Missing env var: MISSING_VAR_XYZ"):
        config.env("MISSING_VAR_XYZ")
