# -*- coding: utf-8 -*-
"""把试用数据导出成可分析的表格与对比摘要。

    python tools/trial_export.py                      # 默认读 .web-data/interviews.sqlite3
    python tools/trial_export.py --out trials         # 输出目录
    python tools/trial_export.py --names              # 保留真实称呼（默认匿名成 P01…）

为什么要有这个工具
------------------
比赛材料里「真实用户验证」不能只有一句「大家觉得不错」。这里把每场练习的可解释指标
落到 CSV：追问轮次、有效作答、陈述单元覆盖、四维得分；再把同一个人的两轮练习配对，
给出前后变化。全部是确定性聚合，不调用模型。

局限要如实写：这是**同人前后测，不是对照实验**；样本量小，只能说明「这次练习之后
有变化」，不能归因。
"""
import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_sessions(db_path: Path) -> list[dict]:
    if not db_path.is_file():
        raise SystemExit(f"找不到数据库：{db_path}")
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    rows = []
    for row in db.execute("SELECT id, payload, report FROM sessions"):
        try:
            session = json.loads(row["payload"])
        except (TypeError, json.JSONDecodeError):
            continue
        if row["report"]:
            try:
                session.setdefault("report", json.loads(row["report"]))
            except json.JSONDecodeError:
                pass
        rows.append(session)
    db.close()
    rows.sort(key=lambda item: item.get("created_at") or "")
    return rows


def labels_for(sessions: list[dict], include_names: bool) -> dict:
    if include_names:
        return {s.get("candidate") or "未命名": s.get("candidate") or "未命名" for s in sessions}
    names = sorted({s.get("candidate") or "未命名" for s in sessions})
    return {name: f"P{index:02d}" for index, name in enumerate(names, 1)}


def _report(session: dict) -> dict:
    report = session.get("report")
    return report if isinstance(report, dict) else {}


def _counts(session: dict, report: dict) -> dict:
    messages = session.get("messages") or []
    answered = sum(1 for m in messages
                   if m.get("role") == "user" and m.get("status") == "completed")
    coverage = report.get("unit_coverage") or {}
    skipped = report.get("skipped_questions") or []
    return {
        "answered": answered,
        "scored": len(report.get("per_question") or []),
        "skipped": len(skipped),
        "coverage": coverage.get("ratio"),
        "covered": coverage.get("covered"),
        "units": coverage.get("total"),
    }


def rows_for(sessions: list[dict], labels: dict) -> list[dict]:
    result = []
    for session in sessions:
        report = _report(session)
        if not report:
            continue
        counts = _counts(session, report)
        created = session.get("created_at") or ""
        result.append({
            "participant": labels.get(session.get("candidate") or "未命名", "—"),
            "date": created[:10],
            "created_at": created,
            "session_id": session.get("id"),
            "scene": session.get("scene") or "interview",
            "rounds": session.get("rounds"),
            "answered": counts["answered"],
            "scored": counts["scored"],
            "skipped": counts["skipped"],
            "coverage": counts["coverage"],
            "covered": counts["covered"],
            "units": counts["units"],
            "overall": report.get("overall"),
            "dims": report.get("dimension_scores") or {},
        })
    return result


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["参与人", "日期", "场次", "场景", "目标轮数", "有效作答", "计分题数",
                         "未计分", "单元覆盖", "覆盖段/总段", "总分", "维度得分"])
        for row in rows:
            dims = "；".join(f"{name} {value}" for name, value in row["dims"].items())
            writer.writerow([
                row["participant"], row["date"], row["session_id"], row["scene"],
                row["rounds"], row["answered"], row["scored"], row["skipped"],
                f"{row['coverage']}" if row["coverage"] is not None else "",
                f"{row['covered']}/{row['units']}" if row["units"] else "",
                row["overall"] if row["overall"] is not None else "",
                dims,
            ])


def _delta(before, after):
    if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
        return None
    return round(float(after) - float(before), 2)


def pair_rounds(rows: list[dict]) -> list[dict]:
    """同一个人按时间配对相邻两场；只取前两场，避免把多次练习混在一起。"""
    by_participant: dict[str, list[dict]] = {}
    for row in rows:
        by_participant.setdefault(row["participant"], []).append(row)
    pairs = []
    for participant, items in sorted(by_participant.items()):
        if len(items) < 2:
            continue
        first, second = items[0], items[1]
        dims = {}
        for name, before in first["dims"].items():
            after = second["dims"].get(name)
            delta = _delta(before, after)
            if delta is not None:
                dims[name] = {"before": before, "after": after, "delta": delta}
        pairs.append({
            "participant": participant,
            "first": first,
            "second": second,
            "overall_delta": _delta(first["overall"], second["overall"]),
            "coverage_delta": _delta(first["coverage"], second["coverage"]),
            "dims": dims,
        })
    return pairs


def _mean(values):
    values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(values) / len(values), 2) if values else None


def build_summary(rows: list[dict], pairs: list[dict]) -> str:
    participants = sorted({row["participant"] for row in rows})
    scenes = {}
    for row in rows:
        scenes[row["scene"]] = scenes.get(row["scene"], 0) + 1
    lines = [
        "# 试用数据摘要",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"- 参与人：{len(participants)} 人",
        f"- 已生成报告的场次：{len(rows)} 场",
        "- 场景分布：" + ("、".join(f"{k} {v} 场" for k, v in scenes.items()) or "无"),
        f"- 完成两轮及以上的参与人：{len(pairs)} 人",
        "",
        "> 这是同一批人的前后测，不是对照实验。样本量小，只能说明「练习后有变化」，"
        "不能把变化归因于本工具。缺失数据和退出的场次不补值。",
        "",
    ]
    if pairs:
        deltas = [p["overall_delta"] for p in pairs if p["overall_delta"] is not None]
        improved = sum(1 for value in deltas if value > 0)
        coverage = [p["coverage_delta"] for p in pairs if p["coverage_delta"] is not None]
        lines += [
            "## 前后对比（第一轮 → 第二轮）",
            "",
            f"- 总分平均变化：{_mean(deltas)}（提升 {improved} 人 / 共 {len(deltas)} 人）",
            f"- 陈述单元覆盖平均变化：{_mean(coverage)}",
            "",
            "| 参与人 | 总分 第一轮 | 总分 第二轮 | 变化 | 覆盖 第一轮 | 覆盖 第二轮 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for pair in pairs:
            lines.append(
                f"| {pair['participant']} | {pair['first']['overall']} | "
                f"{pair['second']['overall']} | {pair['overall_delta']} | "
                f"{pair['first']['coverage']} | {pair['second']['coverage']} |")
        lines += ["", "### 分维度变化（只统计两轮都有的维度）", "",
                  "| 维度 | 人数 | 平均变化 |", "| --- | --- | --- |"]
        names = sorted({name for pair in pairs for name in pair["dims"]})
        for name in names:
            values = [pair["dims"][name]["delta"] for pair in pairs if name in pair["dims"]]
            lines.append(f"| {name} | {len(values)} | {_mean(values)} |")
        lines.append("")
    else:
        lines += ["## 前后对比", "", "还没有完成两轮的参与人。", ""]

    overalls = [row["overall"] for row in rows]
    coverage_all = [row["coverage"] for row in rows if row["coverage"] is not None]
    lines += [
        "## 全部场次",
        "",
        f"- 平均总分：{_mean(overalls)}",
        f"- 平均陈述单元覆盖率：{_mean(coverage_all)}",
        "",
        "## 每人明细",
        "",
        "| 参与人 | 场次 | 日期 | 有效作答 | 计分题 | 覆盖 | 总分 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        coverage = f"{row['covered']}/{row['units']}" if row["units"] else "—"
        lines.append(f"| {row['participant']} | {row['scene']} | {row['date']} | "
                     f"{row['answered']} | {row['scored']} | {coverage} | {row['overall']} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="导出试用数据（CSV + Markdown 摘要）")
    parser.add_argument("--db", default=str(ROOT / ".web-data" / "interviews.sqlite3"))
    parser.add_argument("--out", default=str(ROOT / "trials"))
    parser.add_argument("--names", action="store_true", help="保留真实称呼（默认匿名）")
    args = parser.parse_args(argv)

    sessions = load_sessions(Path(args.db))
    if not sessions:
        print("数据库里没有场次记录。")
        return 1
    labels = labels_for(sessions, args.names)
    rows = rows_for(sessions, labels)
    pairs = pair_rounds(rows)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(rows, out / "sessions.csv")
    (out / "summary.md").write_text(build_summary(rows, pairs), encoding="utf-8")
    print(f"已导出 {len(rows)} 场、{len(pairs)} 组两轮配对 → {out}")
    print("  sessions.csv  每场指标（可直接做图）")
    print("  summary.md    两轮前后对比与每人明细")
    return 0


if __name__ == "__main__":
    sys.exit(main())
