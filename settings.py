# -*- coding: utf-8 -*-
"""环境变量解析的单一入口。

多个模块都要读环境变量；布尔值写法不统一时，`WEB_SPEECH=off` 能关语音，
`PROMPT_CACHE=off` 却可能因为多一个空格而失效。这里只做解析，不保存状态。
"""
import os

TRUE_VALUES = ("1", "true", "yes", "on")
FALSE_VALUES = ("0", "false", "no", "off")


def env_text(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return default


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default