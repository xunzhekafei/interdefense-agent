# -*- coding: utf-8 -*-
"""AI 交互日志导出：过滤噪声、规范化输出。"""
import json

from tools.export_ai_log import parse_session, write_outputs


def _write(tmp_path, lines, name="s.jsonl"):
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in lines),
                    encoding="utf-8")
    return path


def test_parse_keeps_only_user_and_assistant_text(tmp_path):
    path = _write(tmp_path, [
        {"type": "user", "timestamp": "2026-11-25T00:00:00Z",
         "message": {"role": "user", "content": [{"type": "text", "text": "开始吧"}]}},
        {"type": "assistant", "timestamp": "2026-11-25T00:00:01Z",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "text": "内部思考"}, {"type": "text", "text": "好的"}]}},
        {"type": "user", "timestamp": "2026-11-25T00:00:02Z", "isMeta": True,
         "message": {"role": "user", "content": "系统注入的提示"}},
        {"type": "user", "timestamp": "2026-11-25T00:00:03Z",
         "message": {"role": "user", "content": [{"type": "tool_result", "content": "很长的结果"}]}},
        {"type": "api-request", "timestamp": "2026-11-25T00:00:04Z"},
    ])
    events = parse_session(path, max_chars=100)
    assert [event["text"] for event in events] == ["开始吧", "好的"]
    assert [event["role"] for event in events] == ["user", "assistant"]


def test_long_message_is_truncated(tmp_path):
    path = _write(tmp_path, [
        {"type": "user", "timestamp": "2026-11-25T00:00:00Z",
         "message": {"role": "user", "content": "字" * 50}},
    ])
    events = parse_session(path, max_chars=10)
    assert events[0]["text"].startswith("字" * 10)
    assert "截断" in events[0]["text"]


def test_outputs_are_normalized_jsonl_and_markdown(tmp_path):
    events = [{"ts": "2026-11-25T00:00:00Z", "role": "user", "text": "你好"}]
    markdown, normalized = write_outputs(tmp_path / "abc.jsonl", events, tmp_path / "logs",
                                         "someone", max_chars=100)
    assert markdown.exists() and normalized.exists()
    assert markdown.parent.name == "2026-11-25"
    first = json.loads(normalized.read_text(encoding="utf-8").splitlines()[0])
    assert first["session_id"] == "abc"
    assert first["tool"] == "claude-code"
    assert first["seq"] == 0
    assert "你好" in markdown.read_text(encoding="utf-8")
