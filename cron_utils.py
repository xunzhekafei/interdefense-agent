# -*- coding: utf-8 -*-
"""5 段 cron 表达式的匹配与校验（从 agent.py 抽出的纯函数）。

不持有任何全局状态：agent.py 的调度器仍然管理 job、队列和线程，
这里只回答两个问题——表达式合不合法、这个时刻该不该触发。
"""
import datetime


def _field_matches(field: str, value: int) -> bool:
    if field == "*":
        return True
    if field.startswith("*/"):
        return value % int(field[2:]) == 0
    if "," in field:
        return any(_field_matches(part.strip(), value) for part in field.split(","))
    if "-" in field:
        start, end = field.split("-", 1)
        return int(start) <= value <= int(end)
    return value == int(field)


def cron_matches(cron_expr: str, moment: datetime.datetime) -> bool:
    """5 段 cron 匹配；日期/星期同时给定时按标准语义取「或」（任一匹配即触发）。"""
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return False
    minute, hour, day, month, weekday = fields
    cron_weekday = (moment.weekday() + 1) % 7  # 转成 cron 的 0=周日
    if not (_field_matches(minute, moment.minute)
            and _field_matches(hour, moment.hour)
            and _field_matches(month, moment.month)):
        return False
    day_matches = _field_matches(day, moment.day)
    weekday_matches = _field_matches(weekday, cron_weekday)
    if day == "*" and weekday == "*":
        return True
    if day == "*":
        return weekday_matches
    if weekday == "*":
        return day_matches
    return day_matches or weekday_matches


def validate_cron(cron_expr: str) -> str | None:
    """校验 5 段 cron 表达式，返回错误信息或 None。"""
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        return f"需要 5 段（分 时 日 月 星期），实际 {len(fields)} 段"
    rules = [("分钟", 0, 59), ("小时", 0, 23), ("日", 1, 31), ("月", 1, 12), ("星期", 0, 6)]
    for field, (name, lo, hi) in zip(fields, rules):
        error = _validate_field(field, lo, hi)
        if error:
            return f"{name}: {error}"
    return None


def _validate_field(field: str, lo: int, hi: int) -> str | None:
    if field == "*":
        return None
    if field.startswith("*/"):
        step = field[2:]
        if not step.isdigit() or int(step) <= 0:
            return f"非法步长 {field}"
        return None
    if "," in field:
        for part in field.split(","):
            error = _validate_field(part.strip(), lo, hi)
            if error:
                return error
        return None
    if "-" in field:
        start, end = field.split("-", 1)
        if not start.isdigit() or not end.isdigit():
            return f"非法区间 {field}"
        if int(start) > int(end):
            return f"区间起点大于终点 {field}"
        if int(start) < lo or int(end) > hi:
            return f"区间 {field} 超出 [{lo}-{hi}]"
        return None
    if not field.isdigit():
        return f"非法字段 {field}"
    if not (lo <= int(field) <= hi):
        return f"取值 {field} 超出 [{lo}-{hi}]"
    return None