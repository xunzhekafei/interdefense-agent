# -*- coding: utf-8 -*-
"""陈述单元：切分、标记解析、证据回链与场次集成。

全部离线，不调用模型。
"""
import time

from backend.agent_adapter import answered_qa
from backend.service import InterviewService
from script_units import (coverage, segment, render, resolve_refs, split_markers,
                          unit_of_question, unit_of_quote)

SCRIPT = """## 研究背景
毕设做的是面向高校的课程知识问答。现有系统回答不了跨章节的问题。

## 研究方法
我们用了检索增强生成，先做向量召回，再用重排模型。
数据来自三个学期的课程资料，共 1.2 万条。

## 实验结果
准确率从 62% 提升到 81%，人工评估的一致性也在 0.7 以上。

## 创新点
我的工作是设计了章节级切分策略，并补了 800 条人工标注。

## 不足与展望
样本只覆盖两门课，后续要扩到更多学科。
"""


# ---------- 切分 ----------

def test_segment_maps_sections_and_ids():
    units = segment(SCRIPT)
    assert [unit["id"] for unit in units] == [f"U{index}" for index in range(1, len(units) + 1)]
    assert {unit["section"] for unit in units} == {"背景", "方法", "结果", "创新", "局限"}


def test_segment_offsets_point_back_to_original():
    """报告回链的前提：每个单元都能在原文里原样定位。"""
    units = segment(SCRIPT)
    for unit in units:
        assert SCRIPT[unit["start"]:unit["end"]] == unit["text"]
        assert unit["text"].strip() == unit["text"]


def test_segment_strips_headings_from_unit_text():
    """标题只用来判段落类型，不进正文：报告里不该出现「## 研究背景」。"""
    units = segment(SCRIPT)
    assert all("##" not in unit["text"] for unit in units)
    assert units[0]["section"] == "背景"
    assert units[0]["text"].startswith("毕设做的是面向高校的课程知识问答")
    # 去掉标题后偏移仍然逐字对应
    for unit in units:
        assert SCRIPT[unit["start"]:unit["end"]] == unit["text"]


def test_segment_empty_script():
    assert segment("") == []
    assert segment("   \n\n  ") == []


def test_segment_without_headings_uses_keywords():
    text = ("研究背景：现有课程问答系统无法回答跨章节的问题。\n\n"
            "我们采用检索增强生成的方法，先召回再重排。\n\n"
            "结果显示准确率提升了 19 个百分点。")
    sections = {unit["section"] for unit in segment(text)}
    assert {"背景", "方法", "结果"} <= sections


def test_long_block_split_respects_limit():
    text = "这是一句用于测试切分的中文句子。" * 100
    units = segment(text, max_chars=100)
    assert len(units) > 1
    assert all(len(unit["text"]) <= 100 for unit in units)


def test_short_block_is_merged_into_previous():
    text = ("研究背景：这是一个足够长的背景描述，说明现有系统存在的问题。\n\n"
            "好的\n\n"
            "我们采用了检索增强生成的方法来解决问题，并且补充了人工标注数据。")
    units = segment(text)
    assert all(unit["text"] != "好的" for unit in units)


def test_too_many_units_merge_instead_of_drop():
    text = "\n\n".join(f"## 第{index}节\n这是第{index}节的结论，指标提升了 {index} 个百分点，"
                       "样本覆盖三个学期。" for index in range(1, 11))
    units = segment(text, max_units=3)
    assert len(units) == 3
    assert "第1节" in units[0]["text"]
    assert "第10节" in units[-1]["text"]
    assert "第5节" in "".join(unit["text"] for unit in units)


def test_render_contains_ids_and_rules():
    text = render(segment(SCRIPT))
    assert "U1" in text and "[[U3]]" in text
    assert "不得编造编号" in text


def test_render_respects_limit():
    assert len(render(segment(SCRIPT), limit_chars=80)) <= 80


# ---------- 追问标记 ----------

def test_split_markers_removes_marker():
    clean, refs = split_markers("这里的基线是多少？[[U2]]")
    assert clean == "这里的基线是多少？"
    assert refs == ["U2"]


def test_split_markers_supports_multiple_and_lowercase():
    _, refs = split_markers("[[u2,U5]]改用了什么方案？[[U2]]")
    assert refs == ["U2", "U5"]


def test_split_markers_leaves_text_without_marker():
    assert split_markers("这个方案怎么拆的？") == ("这个方案怎么拆的？", [])


def test_resolve_refs_drops_unknown_ids():
    units = segment(SCRIPT)
    assert resolve_refs(units, ["U1", "U99", "bad"]) == ["U1"]
    assert resolve_refs(units, ["U1", "u1"]) == ["U1"]


# ---------- 证据回链与覆盖 ----------

def test_unit_of_quote_links_evidence():
    units = segment(SCRIPT)
    quote = "先做向量召回，再用重排模型"
    assert unit_of_quote(units, quote) == "U2"
    assert unit_of_quote(units, "这句话不在这份讲稿里") is None
    assert unit_of_quote(units, "") is None


def test_unit_of_question_links_paraphrased_question():
    """模型漏写标记时用问题回链：共享原文片段够长才链，纯语义改写不猜。

    「你说准确率提升了 19 个百分点」与原文只共享「准确率」三字，按设计不链——
    宁可让报告说这一段没问到，也不要链错一段。
    """
    units = segment(SCRIPT)
    assert unit_of_question(units, "你说准确率从 62% 提升到 81%，测了多少条数据？") == "U3"
    assert unit_of_question(units, "你说先做向量召回、再用重排模型，召回用的什么？") == "U2"
    assert unit_of_question(units, "你说准确率提升了 19 个百分点，基线是多少？") is None
    assert unit_of_question(units, "你觉得这个课题的意义是什么？") is None
    assert unit_of_question(units, "你刚才提到很多工具，怎么看这个市场？") is None


def test_coverage_counts_references_and_uncovered():
    units = segment(SCRIPT)
    result = coverage(units, [
        {"question": "基线？", "unit_ref": ["U2"]},
        {"question": "样本？", "unit_ref": ["U2", "U3"]},
    ])
    assert result["total"] == len(units)
    assert result["covered"] == 2
    assert result["units"][1]["references"] == 2
    assert {row["id"] for row in result["uncovered"]} == {"U1", "U4", "U5"}


# ---------- 场次集成 ----------

class ScriptedAgent:
    """答辩场景：面试官每次追问都锚定 U2。"""

    def __init__(self, reply_text="这里的基线是多少？[[U2]]"):
        self.reply_text = reply_text

    def configured(self):
        return True

    def reply(self, session, emit, cancel, directory=None):
        return self.reply_text

    def report(self, session, emit, cancel, directory):
        return {}


def _wait_done(service, session_id, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        session = service.store.get(session_id)
        if not session["active_turn"]:
            return session
        time.sleep(0.01)
    raise AssertionError("回合没有在限定时间内结束")


def test_create_builds_units_only_for_defense_scenes(tmp_path):
    service = InterviewService(tmp_path, ScriptedAgent())
    try:
        defense = service.create("甲", "毕业设计答辩", "", scene="defense", script=SCRIPT)
        assert defense["scene"] == "defense"
        assert [unit["id"] for unit in defense["units"]][:2] == ["U1", "U2"]

        interview = service.create("乙", "AI", "")
        assert interview["scene"] == "interview"
        assert interview["units"] == []
    finally:
        service.close()


def test_turn_strips_marker_and_keeps_unit_ref(tmp_path):
    service = InterviewService(tmp_path, ScriptedAgent())
    try:
        session = service.create("甲", "答辩", "", scene="defense", script=SCRIPT)
        service.submit(session["id"], action="start", request_id="a" * 8)
        saved = _wait_done(service, session["id"])
        message = saved["messages"][-1]
        assert message["text"] == "这里的基线是多少？"
        assert message["unit_ref"] == ["U2"]
    finally:
        service.close()


def test_interview_turn_has_empty_unit_ref(tmp_path):
    service = InterviewService(tmp_path, ScriptedAgent("请你解释一下检索增强生成。"))
    try:
        session = service.create("甲", "AI", "")
        service.submit(session["id"], action="start", request_id="a" * 8)
        saved = _wait_done(service, session["id"])
        assert saved["messages"][-1]["text"] == "请你解释一下检索增强生成。"
        assert saved["messages"][-1]["unit_ref"] == []
    finally:
        service.close()


def test_answered_qa_carries_unit_ref():
    qa = answered_qa([
        {"role": "assistant", "text": "样本量是多少？", "status": "completed", "unit_ref": ["U3"]},
        {"role": "user", "text": "两门课共 300 条。", "status": "completed"},
    ])
    assert qa == [{"question": "样本量是多少？", "answer": "两门课共 300 条。", "unit_ref": ["U3"]}]