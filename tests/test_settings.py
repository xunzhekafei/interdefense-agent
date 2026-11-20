"""环境变量解析的行为约定。"""
import settings


def test_env_flag_recognizes_common_spellings(monkeypatch):
    for value in ("1", "true", "YES", " on "):
        monkeypatch.setenv("TEST_FLAG", value)
        assert settings.env_flag("TEST_FLAG", False) is True
    for value in ("0", "false", "NO", " off "):
        monkeypatch.setenv("TEST_FLAG", value)
        assert settings.env_flag("TEST_FLAG", True) is False


def test_env_flag_falls_back_on_missing_or_unknown(monkeypatch):
    monkeypatch.delenv("TEST_FLAG", raising=False)
    assert settings.env_flag("TEST_FLAG", True) is True
    assert settings.env_flag("TEST_FLAG") is False

    monkeypatch.setenv("TEST_FLAG", " ")
    assert settings.env_flag("TEST_FLAG", True) is True

    monkeypatch.setenv("TEST_FLAG", "maybe")
    assert settings.env_flag("TEST_FLAG", True) is True
    assert settings.env_flag("TEST_FLAG", False) is False


def test_env_numbers_fall_back_on_bad_values(monkeypatch):
    monkeypatch.setenv("TEST_INT", "42")
    monkeypatch.setenv("TEST_FLOAT", "0.25")
    assert settings.env_int("TEST_INT", 15) == 42
    assert settings.env_float("TEST_FLOAT", 0.5) == 0.25

    monkeypatch.setenv("TEST_INT", "x")
    monkeypatch.setenv("TEST_FLOAT", "x")
    assert settings.env_int("TEST_INT", 15) == 15
    assert settings.env_float("TEST_FLOAT", 0.5) == 0.5

    monkeypatch.delenv("TEST_INT", raising=False)
    monkeypatch.delenv("TEST_FLOAT", raising=False)
    assert settings.env_int("TEST_INT", 15) == 15
    assert settings.env_float("TEST_FLOAT", 0.5) == 0.5


def test_env_text_strips_whitespace(monkeypatch):
    monkeypatch.setenv("TEST_TEXT", "  value  ")
    assert settings.env_text("TEST_TEXT") == "value"
    assert settings.env_text("TEST_MISSING", "默认") == "默认"