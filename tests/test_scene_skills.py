# -*- coding: utf-8 -*-
"""三场景技能：加载、单元推进计划与缺失技能兜底。

全部离线：用假的 agent_loop 捕获 system prompt，不启动 TestClient。
"""
import threading

import agent
import backend.agent_adapter as adapter
from backend.agent_adapter import InterviewAgent, _unit_plan
from script_units import segment

SCRIPT = """## 研究背景
现有系统无法回答跨章节的问题。

## 研究方法
先做向量召回，再用重排模型。

## 实验结果
准确率从 62% 提升到 81%。

## 创新点
设计了章节级切分策略。

## 不足与展望
样本只覆盖两门课。
"""


def _session(scene, messages=None, rounds=10):
    return {"id": "s1", "candidate": "甲", "role": "答辩", "background": "",
            "pressure": "标准", "rounds": rounds, "scene": scene,
            "script": SCRIPT, "units": segment(SCRIPT),
            "messages": messages or []}


def _capture(monkeypatch):
    captured = {}

    def fake_loop(messages, system, **kwargs):
        captured["system"] = system
        captured["messages"] = messages
        return "下一问"

    monkeypatch.setattr(agent, "agent_loop", fake_loop)
    return captured


# ---------- 技能注册 ----------

def test_new_skills_are_registered():
    for name in ("defense-coach", "course-report-coach"):
        assert name in agent.SKILL_LOADER.skills
        content = agent.SKILL_LOADER.load(name)
        assert not content.startswith("错误：")
        assert "陈述单元" in content


def test_defense_skill_has_scene_rules():
    content = agent.SKILL_LOADER.load("defense-coach")
    assert "答辩评委" in content
    assert "[[U编号]]" in content
    assert "不要问" in content and "自我介绍" in content


def test_course_report_skill_has_scene_rules():
    content = agent.SKILL_LOADER.load("course-report-coach")
    assert "课程助教" in content
    assert "个人贡献" in content
    assert "[[U编号]]" in content


# ---------- 场景 → 技能 ----------

def test_defense_scene_uses_unit_plan_not_round_mix(monkeypatch):
    captured = _capture(monkeypatch)
    InterviewAgent().reply(_session("defense"), lambda *args: None, threading.Event())

    system = captured["system"]
    assert "答辩评委" in system
    assert "本场轮数计划" not in system
    assert "项目深挖" not in system
    assert "陈述单元共" in system and "不设反问" in system
    assert "生成答辩报告" in system
    assert captured["messages"][0]["content"].startswith("开始答辩复盘")


def test_presentation_scene_uses_course_report_skill(monkeypatch):
    captured = _capture(monkeypatch)
    InterviewAgent().reply(_session("presentation"), lambda *args: None, threading.Event())

    system = captured["system"]
    assert "课程助教" in system
    assert "生成汇报报告" in system


def test_interview_scene_keeps_original_round_plan(monkeypatch):
    captured = _capture(monkeypatch)
    session = {"id": "s1", "candidate": "甲", "role": "AI", "background": "",
               "pressure": "标准", "rounds": 10, "messages": []}
    InterviewAgent().reply(session, lambda *args: None, threading.Event())

    system = captured["system"]
    assert "模拟面试官" in system
    assert "本场轮数计划" in system
    assert captured["messages"][0]["content"] == "开始模拟面试，请先让我做自我介绍。"


def test_missing_skill_falls_back_instead_of_leaking_error(monkeypatch):
    monkeypatch.setitem(adapter.SCENE_SKILLS, "defense", "不存在的技能")
    captured = _capture(monkeypatch)
    InterviewAgent().reply(_session("defense"), lambda *args: None, threading.Event())

    system = captured["system"]
    assert "未知技能" not in system
    assert "模拟面试官" in system


# ---------- 单元推进计划 ----------

def test_unit_plan_lists_uncovered_units():
    units = segment(SCRIPT)
    session = {"messages": [
        {"role": "assistant", "text": "Q", "status": "completed",
         "unit_ref": [units[0]["id"]]},
        {"role": "user", "text": "A", "status": "completed"},
    ]}
    text = _unit_plan(session, 10, units)

    assert "已覆盖 1 个" in text
    remaining = text.split("尚未覆盖：", 1)[1]
    assert units[0]["id"] not in remaining
    assert units[1]["id"] in remaining
    assert "最多追问 2 层" in text


def test_unit_plan_marks_complete_when_all_covered():
    units = segment(SCRIPT)
    covered = [unit["id"] for unit in units]
    session = {"messages": [{"role": "assistant", "text": "Q", "status": "completed",
                             "unit_ref": covered}]}
    text = _unit_plan(session, 10, units)

    assert "所有单元已覆盖" in text
    assert "尚未覆盖" not in text

def test_unit_plan_enforces_round_cap():
    """学生选了轮数就必须生效：问满就收尾，不能继续按单元一路问下去。"""
    units = segment(SCRIPT)
    session = {"messages": [
        {"role": "assistant", "text": "Q1", "status": "completed", "unit_ref": ["U1"]},
        {"role": "user", "text": "A1", "status": "completed"},
        {"role": "assistant", "text": "Q2", "status": "completed", "unit_ref": ["U2"]},
        {"role": "user", "text": "A2", "status": "completed"},
        {"role": "assistant", "text": "Q3", "status": "completed", "unit_ref": ["U3"]},
        {"role": "user", "text": "A3", "status": "completed"},
    ]}
    text = _unit_plan(session, 3, units)

    assert "目前已经问了 3 题" in text
    assert "已经达到本场题数上限" in text
    assert "不要再提问" in text
    # 达到上限时不再列出未覆盖清单，避免模型继续"补作业"
    assert "尚未覆盖：" not in text


def test_unit_plan_still_lists_units_before_cap():
    units = segment(SCRIPT)
    session = {"messages": [
        {"role": "user", "text": "A1", "status": "completed"},
        {"role": "user", "text": "A2", "status": "completed"},
    ]}
    text = _unit_plan(session, 10, units)
    assert "目前已经问了 2 题" in text
    assert "尚未覆盖：" in text
    assert "题数硬上限" in text
