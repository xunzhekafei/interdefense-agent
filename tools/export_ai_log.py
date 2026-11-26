# -*- coding: utf-8 -*-
"""把 Claude Code 的会话记录导出成可提交的 AI 交互日志。

    python tools/export_ai_log.py                     # 最近修改的会话
    python tools/export_ai_log.py --file <x.jsonl>    # 指定会话
    python tools/export_ai_log.py --since 2026-11-20  # 只导出这之后的会话（可多个）

产出（默认 logs/ 下）：

    logs/local/<日期>/claude-code__<session>.md    人可读的对话摘录
    logs/local/<日期>/claude-code__<session>.jsonl 精简后的逐条事件

为什么要精简
------------
Claude Code 的原始 JSONL 里混着大量内部记录（请求体、成本状态、文件快照、
工具结果），本项目一个会话就有 30MB+，直接提交既不友好也没必要。这里只保留
用户输入与模型输出的文字，工具调用的结果整段丢弃——模板要的是「提示词与回复
摘录」，不是运行遥测。

隐私
----
导出前请自己检查一遍：对话里是否出现过密钥、账号密码、他人隐私信息。
本工具只做过滤，不会自动脱敏。
"""
import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone


def _mangle(path: pathlib.Path) -> str:
    """Claude Code 用「非字母数字字符替换成 -」的方式给项目目录命名。"""
    return "".join(char if char.isalnum() else "-" for char in str(path))


def find_sessions(root: pathlib.Path, since: datetime | None, project: pathlib.Path | None):
    base = root
    if project is not None:
        base = root / _mangle(project)
        if not base.is_dir():
            raise SystemExit(f"找不到会话目录：{base}")
    files = []
    for path in base.glob("**/*.jsonl"):
        stat = path.stat()
        if since is not None and stat.st_mtime < since.timestamp():
            continue
        files.append(path)
    files.sort(key=lambda p: p.stat().st_mtime)
    return files


def _text_blocks(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n\n".join(parts).strip()


def parse_session(path: pathlib.Path, max_chars: int) -> list[dict]:
    events = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("isMeta"):
                continue
            kind = obj.get("type")
            if kind not in ("user", "assistant"):
                continue
            message = obj.get("message") or {}
            role = message.get("role") or kind
            text = _text_blocks(message.get("content"))
            if not text:
                continue
            # 长粘贴（日志、文件内容）截断，保留开头便于核对
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n……（截断，原文 {len(text)} 字）"
            events.append({
                "ts": obj.get("timestamp") or "",
                "role": role,
                "text": text,
            })
    return events


def write_outputs(path: pathlib.Path, events: list[dict], out_root: pathlib.Path,
                  owner: str, max_chars: int) -> tuple[pathlib.Path, pathlib.Path]:
    session_id = path.stem
    started = events[0]["ts"][:10] if events and events[0]["ts"] else "unknown"
    target = out_root / owner / started
    target.mkdir(parents=True, exist_ok=True)
    stem = f"claude-code__{session_id}"

    lines = [
        f"# AI 交互记录 · {session_id}",
        "",
        f"- 工具：Claude Code",
        f"- 会话开始：{events[0]['ts'] if events else '—'}",
        f"- 事件数：{len(events)}",
        "- 说明：仅保留用户输入与 AI 回复文字；工具调用结果与内部遥测已剔除。",
        "",
    ]
    for event in events:
        who = "用户" if event["role"] == "user" else "Claude"
        lines += [f"## {who} · {event['ts']}", "", event["text"], ""]
    markdown = target / f"{stem}.md"
    markdown.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    normalized = target / f"{stem}.jsonl"
    with normalized.open("w", encoding="utf-8") as handle:
        for index, event in enumerate(events):
            handle.write(json.dumps({
                "schema_version": "1.0",
                "session_id": session_id,
                "tool": "claude-code",
                "seq": index,
                "ts": event["ts"],
                "role": event["role"],
                "text": event["text"],
            }, ensure_ascii=False) + "\n")
    return markdown, normalized


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="导出 Claude Code 会话为 AI 交互日志")
    parser.add_argument("--root", default=str(pathlib.Path.home() / ".claude" / "projects"),
                        help="Claude Code 的会话目录")
    parser.add_argument("--project", default=None,
                        help="只看某个工作目录对应的会话（传目录路径）")
    parser.add_argument("--file", default=None, help="直接指定一个 .jsonl")
    parser.add_argument("--since", default=None, help="只导出该日期之后的会话（YYYY-MM-DD）")
    parser.add_argument("--out", default="logs", help="输出目录")
    parser.add_argument("--owner", default="local", help="子目录名，通常是 GitHub 用户名")
    parser.add_argument("--max-chars", type=int, default=6000, help="单条消息最多保留多少字")
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).expanduser()
    since = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    project = pathlib.Path(args.project).expanduser() if args.project else None

    if args.file:
        files = [pathlib.Path(args.file).expanduser()]
    else:
        files = find_sessions(root, since, project)
    if not files:
        print("没有找到会话记录。")
        return 1

    total = 0
    for path in files:
        events = parse_session(path, args.max_chars)
        if not events:
            continue
        markdown, normalized = write_outputs(path, events, pathlib.Path(args.out),
                                             args.owner, args.max_chars)
        print(f"{path.name} → {markdown}（{len(events)} 条）")
        total += 1
    if total == 0:
        print("会话里没有可导出的文字内容。")
        return 1
    print(f"共导出 {total} 个会话。提交前请检查是否包含敏感信息。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
