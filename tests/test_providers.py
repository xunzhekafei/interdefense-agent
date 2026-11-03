# -*- coding: utf-8 -*-
"""提供商配置：默认 Kimi，鉴权方式按提供商切换，环境变量可覆盖。"""
import providers


def _clear(monkeypatch):
    for name in ("PROVIDER", "MODEL", "AUX_MODEL", "ANTHROPIC_BASE_URL",
                 "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                 "REASONING_EFFORT", "PROMPT_CACHE", "THINKING"):
        monkeypatch.delenv(name, raising=False)


def test_default_provider_is_kimi(monkeypatch):
    _clear(monkeypatch)
    p = providers.resolve()
    assert p.name == "kimi"
    assert p.base_url == "https://api.moonshot.cn/anthropic"
    assert p.model == "kimi-k3.1-pro"
    assert p.auth == "bearer"
    assert p.thinking is False
    assert p.effort == "low"


def test_deepseek_provider_defaults(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PROVIDER", "deepseek")
    p = providers.resolve()
    assert p.base_url == "https://api.deepseek.com/anthropic"
    assert p.model == "claude-haiku-4-5"
    assert p.auth == "x-api-key"
    assert p.thinking is True
    assert p.effort is None


def test_model_can_be_overridden(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PROVIDER", "kimi")
    monkeypatch.setenv("MODEL", "kimi-test")
    p = providers.resolve()
    assert p.model == "kimi-test"
    assert p.aux_model == "kimi-k3.1-pro"   # 辅模型有自己的默认值，不跟着主模型变贵

    monkeypatch.setenv("AUX_MODEL", "kimi-aux")
    assert providers.resolve().aux_model == "kimi-aux"


def test_stale_base_url_does_not_leak_across_providers(monkeypatch):
    """切到 Kimi 时，环境里残留的 DeepSeek 地址不能生效。"""
    _clear(monkeypatch)
    monkeypatch.setenv("PROVIDER", "kimi")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
    assert providers.resolve().base_url == "https://api.moonshot.cn/anthropic"


def test_custom_provider_requires_base_url(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PROVIDER", "custom")
    monkeypatch.setenv("MODEL", "qwen2.5:7b")
    try:
        providers.resolve()
    except ValueError as error:
        assert "ANTHROPIC_BASE_URL" in str(error)
    else:
        raise AssertionError("custom 缺少地址时应当报错")

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:11434")
    p = providers.resolve()
    assert p.base_url == "http://localhost:11434"
    assert p.model == "qwen2.5:7b"


def test_credentials_use_bearer_for_kimi(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PROVIDER", "kimi")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-kimi")
    assert providers.credentials() == (None, "sk-kimi")


def test_credentials_use_x_api_key_for_deepseek(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PROVIDER", "deepseek")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-deepseek")
    assert providers.credentials() == ("sk-deepseek", None)


def test_explicit_auth_token_wins(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PROVIDER", "deepseek")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ignored")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-token")
    assert providers.credentials() == (None, "sk-token")


def test_credentials_empty_without_key(monkeypatch):
    _clear(monkeypatch)
    assert providers.credentials() == (None, None)


def test_reasoning_effort_override_and_off(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PROVIDER", "kimi")
    monkeypatch.setenv("REASONING_EFFORT", "high")
    assert providers.resolve().effort == "high"
    monkeypatch.setenv("REASONING_EFFORT", "off")
    assert providers.resolve().effort is None
    monkeypatch.setenv("REASONING_EFFORT", "bogus")
    assert providers.resolve().effort == "low"     # 非法值回落到默认


def test_cache_and_thinking_flags(monkeypatch):
    _clear(monkeypatch)
    assert providers.prompt_cache_enabled() is True
    assert providers.thinking_enabled() is True
    monkeypatch.setenv("PROMPT_CACHE", "off")
    monkeypatch.setenv("THINKING", "0")
    assert providers.prompt_cache_enabled() is False
    assert providers.thinking_enabled() is False
