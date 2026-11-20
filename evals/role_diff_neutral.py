# -*- coding: utf-8 -*-
"""中性回答下的岗位差异化评测。

    python evals/role_diff_neutral.py

默认每个岗位 5 场、每场 10 轮（可用 --sessions / --turns 调整）。

与 role_diff_eval.py 的区别：所有岗位共用同一套中性回答，回答里不出现
ANR / UIKit / 超卖 / 限流等岗位关键词。这样面试官的提问方向只能来自
岗位配置与题库路由，而不是被候选人的回答“喂”出来的。

结果写入 evals/results/role_diff_neutral/，支持断点续跑。
"""
import argparse
import json
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from role_diff_eval import ROLES, analyze, message  # noqa: E402

NEUTRAL_ANSWERS = [
    "我最近几年主要在一个中等规模的业务系统里做开发，负责需求分析、方案设计、编码和上线，也参与过线上问题处理。",
    "项目里我负责一个核心模块，和产品、测试、运维都有协作。上线前会做评审和回归，上线后看监控。",
    "有一次用户反馈慢，我们先看监控和日志，定位到一个高频路径上的资源开销，做了优化并补了监控。",
    "故障处理上，我会先止损，比如回滚或降级，然后再定位根因，最后补监控和流程。",
    "技术选型时我们对比了几种方案，考虑团队熟悉度、维护成本和扩展性，最后选了一个折中方案。",
    "协作中遇到过意见不一致，我会把目标和约束摆出来，用数据和试验结果做决定。",
    "我也参与过一些基础建设，比如自动化测试、CI 流程和文档，减少重复劳动。",
    "如果重来一次，我会更早做压测和监控，提前暴露风险。",
    "我比较关注代码质量和可维护性，评审时会看边界条件和失败处理。",
    "我的问题：团队现在的研发流程和发布节奏是怎样的？",
]


def now():
    return datetime.now(timezone.utc).isoformat()


def run_session(agent_cls, role: str, session_index: int, turns: int, output_dir: Path):
    session = {
        "id": f"neutral-{role}-{session_index}",
        "candidate": "评估候选人",
        "role": role,
        "background": "5 年相关经验，做过中等规模项目。",
        "pressure": "标准",
        "rounds": turns,
        "messages": [],
        "memory": None,
        "memory_version": 0,
    }
    agent = agent_cls()
    questions, errors = [], []
    for turn in range(turns):
        turn_id = uuid.uuid4().hex
        cancel = threading.Event()
        events = []

        def emit(event_type, data):
            events.append((event_type, data))

        text, last_error = "", None
        for attempt in range(3):
            events.clear()
            try:
                text = agent.reply(session, emit, cancel, output_dir / session["id"])
                text = re.sub(r"\s+", " ", text or "").strip()
                if not text:
                    text = "".join(
                        str(data.get("text", "")) for kind, data in events
                        if kind == "reply.delta").strip()
                if text:
                    break
                last_error = ValueError("模型返回空文本")
            except Exception as error:
                last_error = error
                time.sleep(2 + attempt * 3)
        if not text:
            cause = repr(getattr(last_error, "__cause__", None))
            errors.append({"turn": turn + 1,
                           "error": type(last_error).__name__ if last_error else "EmptyReply",
                           "message": (str(last_error)[:160] + " | cause=" + cause)[:300]})
            break
        questions.append(text)
        session["messages"].append(message(turn_id, "assistant", text))
        answer = NEUTRAL_ANSWERS[turn % len(NEUTRAL_ANSWERS)]
        session["messages"].append(message(turn_id, "user", f"第 {turn + 1} 轮补充：{answer}"))
        time.sleep(0.5)
    return {"role": role, "session": session_index, "questions": questions, "errors": errors}


def write_markdown(report, path: Path, roles):
    lines = ["# 中性回答下的岗位差异化评测", "",
             "所有岗位共用同一套中性回答；回答中不含岗位术语。",
             "统计只取技术轮，排除最后的反问。", "",
             "| 岗位 | 问题数 | 唯一问题 | 岗位内重复率 | 分类命中率 | 与其他岗位平均相似度 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for role in roles:
        data = report["roles"].get(role, {})
        lines.append(f"| {role} | {data.get('questions', 0)} | {data.get('unique', 0)} | "
                     f"{data.get('repeat_rate', 0):.0%} | {data.get('hint_rate', 0):.0%} | "
                     f"{report['cross_role_average'].get(role, 0):.3f} |")
    lines += ["", "## 岗位间相似度（越低越差异化）", "", "| 岗位 | " + " | ".join(roles) + " |",
              "| --- | " + " | ".join("---" for _ in roles) + " |"]
    for role in roles:
        lines.append(f"| {role} | " + " | ".join(
            f"{report['similarity'][role][other]:.3f}" for other in roles) + " |")
    lines += ["", "## 每岗位题目样例", ""]
    for role in roles:
        lines.append(f"### {role}")
        for sample in report["roles"].get(role, {}).get("samples", []):
            lines.append(f"- {sample}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roles", default=",".join(ROLES))
    parser.add_argument("--sessions", type=int, default=5)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--output", default="evals/results/role_diff_neutral")
    args = parser.parse_args()
    roles = [role.strip() for role in args.roles.split(",") if role.strip()]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "raw.jsonl"

    rows = []
    if raw_path.exists():
        rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    done = {(row["role"], row["session"]) for row in rows}

    from backend.agent_adapter import InterviewAgent

    for role in roles:
        for index in range(1, args.sessions + 1):
            if (role, index) in done:
                continue
            started = time.perf_counter()
            row = run_session(InterviewAgent, role, index, args.turns, output)
            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)
            elapsed = time.perf_counter() - started
            print(f"{role} 第 {index}/{args.sessions} 场：{len(row['questions'])}/{args.turns} 轮，"
                  f"{elapsed:.1f}s，错误 {len(row['errors'])}", flush=True)

    report = analyze(rows, roles)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, output / "report.md", roles)
    print("报告：", output / "report.md", flush=True)


if __name__ == "__main__":
    main()