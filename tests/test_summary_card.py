# -*- coding: utf-8 -*-
"""摘要卡：规则兜底、模型结果校验、修正与下一场检验点。

全部离线：service 用假 adapter（summarize 返回 None，走规则路径）。
"""
import threading

import pytest

import agent
from backend.agent_adapter import InterviewAgent
from backend.service import InterviewService
from script_summary import (apply_edits, build_card, confirm, focus_checks,
                            focus_items, normalize, rule_questions)
from script_units import segment

SCRIPT = """## 研究背景
现有系统无法回答跨章节的问题。

## 研究方法
方法采用检索增强生成，先召回再重排。

## 实验结果
准确率从 62% 提升到 81%。

## 创新点
提出了章节级切分策略。

## 不足与展望
样本只覆盖两门课，后续要扩展。
"""


def _units():
    return segment(SCRIPT)


# ---------- 规则生成与模型结果校验 ----------

def test_rule_card_covers_every_unit():
    card = build_card(_units())
    assert len(card["claims"]) == len(_units())
    assert [claim["unit_ref"] for claim in card["claims"]] == [u["id"] for u in _units()]
    assert card["version"] == 1
    assert card["confirmed"] is False
    assert card["source"] == "rules"
    # 标题只是分段标记，主张必须来自正文
    assert all("##" not in claim["text"] for claim in card["claims"])


def test_build_card_marks_model_source():
    raw = {"claims": [{"text": "用了检索增强生成", "unit_id": "U2"}],
           "open_questions": [{"text": "样本量是多少？", "unit_id": "U3"}]}
    card = build_card(_units(), raw)
    assert card["source"] == "model"


def test_rule_questions_hit_missing_evidence():
    questions = rule_questions(_units())
    joined = " ".join(item["text"] for item in questions)
    assert "基线" in joined
    assert "已有工作" in joined or "方法的输入" in joined
    assert all(item["unit_ref"].startswith("U") for item in questions)


def test_normalize_drops_invented_unit_ids():
    units = _units()
    raw = {"claims": [{"text": "用了检索增强生成", "unit_id": "U2"},
                      {"text": "编造的一条", "unit_id": "U99"}],
           "open_questions": [{"text": "样本量是多少？", "unit_ref": "U3"}]}
    claims, questions = normalize(raw, units)
    assert [claim["unit_ref"] for claim in claims] == ["U2"]
    assert [question["unit_ref"] for question in questions] == ["U3"]
    assert claims[0]["id"] == "C1"


def test_build_card_falls_back_when_model_returns_empty():
    card = build_card(_units(), {"claims": [], "open_questions": []})
    assert len(card["claims"]) == len(_units())
    assert card["open_questions"]


# ---------- 修正与确认 ----------

def test_apply_edits_confirm_reject_and_rewrite():
    card = build_card(_units())
    edited = apply_edits(card, claims=[
        {"id": "C1", "status": "rejected"},
        {"id": "C2", "status": "confirmed", "edited_text": "我负责检索与重排"},
    ])
    assert edited["claims"][0]["status"] == "rejected"
    assert edited["claims"][1]["status"] == "confirmed"
    assert edited["claims"][1]["edited_text"] == "我负责检索与重排"


def test_apply_edits_ignores_unknown_id_and_bad_status():
    card = build_card(_units())
    edited = apply_edits(card, claims=[
        {"id": "C99", "status": "confirmed"},
        {"id": "C2", "status": "bogus"},
    ])
    assert edited["claims"][1]["status"] == "pending"


def test_confirm_keeps_rejected_and_confirms_pending():
    card = apply_edits(build_card(_units()), claims=[{"id": "C1", "status": "rejected"}])
    confirmed = confirm(card)
    assert confirmed["claims"][0]["status"] == "rejected"
    assert all(item["status"] in ("confirmed", "rejected") for item in confirmed["claims"])
    assert confirmed["confirmed"] is True


# ---------- 检验点 ----------

def test_focus_items_use_edited_text_and_skip_dismissed():
    card = build_card(_units())
    card = apply_edits(card, claims=[{"id": "C1", "status": "rejected"},
                                     {"id": "C2", "status": "confirmed",
                                      "edited_text": "我负责检索与重排"}],
                       open_questions=[{"id": "Q1", "status": "dismissed"}])
    confirmed = confirm(card)
    items = focus_items(confirmed, _units())

    assert len(items) <= 5
    assert all(item["id"] != "C1" for item in items)
    assert all(item["id"] != "Q1" for item in items)
    claim = next(item for item in items if item["id"] == "C2")
    assert claim["text"] == "我负责检索与重排"
    assert claim["quote"]


def test_focus_checks_marks_covered_and_missing():
    focus = [{"text": "样本量", "quote": "准确率从 62% 提升到 81%"}]
    covered = focus_checks(focus, [{"question": "准确率从 62% 提升到 81% 是怎么测的？",
                                    "answer": "在三个学期的数据上。"}])
    missing = focus_checks(focus, [{"question": "你的创新点是什么？", "answer": "章节切分。"}])
    assert covered[0]["checked"] is True
    assert missing[0]["checked"] is False


# ---------- 场次集成 ----------

class CardAgent:
    """没有 summarize 结果，强制走规则兜底。"""

    def configured(self):
        return True

    def summarize(self, session):
        return None

    def reply(self, session, emit, cancel, directory=None):
        return "下一问"

    def report(self, session, emit, cancel, directory):
        return {}


def _wait_done(service, session_id, timeout=5):
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session = service.store.get(session_id)
        if not session["active_turn"]:
            return session
        time.sleep(0.01)
    raise AssertionError("回合没有在限定时间内结束")


def test_service_generates_confirms_and_inherits_focus(tmp_path):
    service = InterviewService(tmp_path, CardAgent())
    try:
        session = service.create("甲", "答辩", "", scene="defense", script=SCRIPT)
        card = service.summary_card(session["id"])
        assert card["claims"] and card["open_questions"]
        # 已有卡片时不重复生成（store 读出来是新对象，比较内容而不是身份）
        assert service.summary_card(session["id"]) == card

        edited = service.patch_summary_card(session["id"], claims=[
            {"id": "C1", "status": "rejected"},
            {"id": "C2", "status": "confirmed", "edited_text": "我负责检索与重排"}])
        assert edited["claims"][0]["status"] == "rejected"

        result = service.confirm_summary_card(session["id"])
        assert result["summary_card"]["confirmed_at"]
        focus = result["focus"]
        assert focus and all(item["id"] != "C1" for item in focus)

        nxt = service.create("甲", "答辩", "", scene="defense", script=SCRIPT,
                             focus_from=session["id"])
        assert nxt["focus"] == focus
        assert nxt["focus_from"] == session["id"]
    finally:
        service.close()


def test_service_rejects_card_without_units(tmp_path):
    service = InterviewService(tmp_path, CardAgent())
    try:
        session = service.create("甲", "AI", "")
        with pytest.raises(ValueError):
            service.summary_card(session["id"])
    finally:
        service.close()


def test_create_rejects_unknown_focus_source(tmp_path):
    service = InterviewService(tmp_path, CardAgent())
    try:
        with pytest.raises(ValueError):
            service.create("甲", "答辩", "", scene="defense", script=SCRIPT,
                           focus_from="missing")
    finally:
        service.close()


def test_reply_injects_focus_points(monkeypatch):
    captured = {}

    def fake_loop(messages, system, **kwargs):
        captured["system"] = system
        return "下一问"

    monkeypatch.setattr(agent, "agent_loop", fake_loop)
    session = {"id": "s1", "candidate": "甲", "role": "答辩", "background": "",
               "pressure": "标准", "rounds": 10, "scene": "defense",
               "units": _units(), "messages": [],
               "focus": [{"kind": "claim", "id": "C2", "text": "我负责检索与重排",
                          "quote": "方法采用检索增强生成", "unit_ref": "U2"}]}
    InterviewAgent().reply(session, lambda *args: None, threading.Event())
    assert "上一场确认的待检验点" in captured["system"]
    assert "我负责检索与重排" in captured["system"]

# ---------- 路由与请求模型 ----------

def test_summary_card_routes_and_input_fields(tmp_path):
    """不启动 TestClient（沙箱禁止回环 socket），只检查路由注册与字段透传。"""
    from fastapi.routing import APIRoute

    from backend.app import SessionInput, create_app

    model = SessionInput(candidate="甲", role="答辩", scene="defense",
                         script="正文", focus_from="abc")
    assert model.model_dump()["focus_from"] == "abc"

    app = create_app(tmp_path, CardAgent(), recognizer=None)
    routes = {(route.path, method) for route in app.routes
              if isinstance(route, APIRoute) for method in route.methods}
    assert ("/api/sessions/{session_id}/summary-card", "POST") in routes
    assert ("/api/sessions/{session_id}/summary-card", "PATCH") in routes
    assert ("/api/sessions/{session_id}/summary-card/confirm", "POST") in routes