# -*- coding: utf-8 -*-
"""模型提供商：接口地址、模型名、鉴权方式的唯一来源。

切换提供商只改环境变量，不动代码：

    PROVIDER=kimi          # 默认；kimi / deepseek / custom
    PROVIDER=deepseek      # 回到 DeepSeek

各字段都可以单独覆盖：`ANTHROPIC_BASE_URL`、`MODEL`、`AUX_MODEL`。

两家的协议差异（都在这里吸收）：
- Kimi 只认 `Authorization: Bearer`，DeepSeek 用 `x-api-key`；
- Kimi K3.1 Pro 始终思考、没有开关，只能用 `output_config.effort` 调深度；
- DeepSeek 用 Anthropic 的 `thinking: {"type": "adaptive"}`。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

EFFORTS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    aux_model: str
    auth: str            # "bearer" 或 "x-api-key"
    thinking: bool       # 是否发送 Anthropic 的 thinking 参数
    effort: str | None   # output_config.effort；None 表示不发送


PROVIDERS = {
    "kimi": Provider(
        name="kimi",
        base_url="https://api.moonshot.cn/anthropic",
        model="kimi-k3.1-pro",
        aux_model="kimi-k3.1-pro",
        auth="bearer",
        thinking=False,     # K3.1 Pro 始终思考，没有开关
        effort="low",       # 面试对话优先速度；质量不够时设 REASONING_EFFORT=high
    ),
    "deepseek": Provider(
        name="deepseek",
        base_url="https://api.deepseek.com/anthropic",
        model="claude-haiku-4-5",   # 映射 deepseek-v4-flash
        aux_model="claude-haiku-4-5",
        auth="x-api-key",
        thinking=True,
        effort=None,
    ),
    # 本地模型 / 其它兼容端点：地址和模型名必须由环境变量给出
    "custom": Provider(
        name="custom",
        base_url="",
        model="",
        aux_model="",
        auth="x-api-key",
        thinking=True,
        effort=None,
    ),
}


def _effort(default: str | None) -> str | None:
    """REASONING_EFFORT 可覆盖；off/none/空字符串表示不发送。"""
    raw = os.environ.get("REASONING_EFFORT")
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in ("", "off", "none", "0", "false", "no"):
        return None
    return value if value in EFFORTS else default


def resolve() -> Provider:
    """读环境变量，返回当前生效的提供商配置。

    接口地址由 PROVIDER 决定——**不用 ANTHROPIC_BASE_URL 覆盖**，避免切到 Kimi
    时还残留着指向 DeepSeek 的旧变量。要换地址就设 `PROVIDER=custom` 并给出
    `ANTHROPIC_BASE_URL`（本地模型、代理、国际站都走这条路）。
    """
    name = (os.environ.get("PROVIDER") or "kimi").strip().lower()
    base = PROVIDERS.get(name, PROVIDERS["custom"])
    if name == "custom":
        base_url = (os.environ.get("ANTHROPIC_BASE_URL") or "").strip()
        if not base_url:
            raise ValueError("PROVIDER=custom 时必须设置 ANTHROPIC_BASE_URL")
    else:
        base_url = base.base_url
    model = os.environ.get("MODEL") or base.model
    return Provider(
        name=name,
        base_url=base_url,
        model=model,
        aux_model=os.environ.get("AUX_MODEL") or base.aux_model or model,
        auth=base.auth,
        thinking=base.thinking,
        effort=_effort(base.effort),
    )


def credentials(provider: Provider | None = None) -> tuple[str | None, str | None]:
    """返回 (api_key, auth_token)。

    显式设置 `ANTHROPIC_AUTH_TOKEN` 时优先用它；否则按提供商的鉴权方式
    决定把 `ANTHROPIC_API_KEY` 当成 Bearer token 还是 x-api-key。
    """
    provider = provider or resolve()
    token = (os.environ.get("ANTHROPIC_AUTH_TOKEN") or "").strip()
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if token:
        return None, token
    if not key:
        return None, None
    if provider.auth == "bearer":
        return None, key
    return key, None


def prompt_cache_enabled() -> bool:
    return _flag("PROMPT_CACHE", True)


def thinking_enabled() -> bool:
    return _flag("THINKING", True)


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("off", "0", "false", "no")
