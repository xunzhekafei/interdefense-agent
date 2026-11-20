"""字节算法题库：结构、来源与检索。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "interview" / "data" / "algorithm_questions.json"


def test_algorithm_bank_shape():
    records = json.loads(BANK.read_text(encoding="utf-8"))
    assert len(records) >= 120
    assert all(record["role"] == "算法工程师" for record in records)
    assert len({record["question"] for record in records}) == len(records)
    assert all(record["source"] == "YaxeZhang/Just-Code (MIT)" for record in records)
    assert all(record["company"] == "字节跳动" for record in records)
    categories = {record["category"] for record in records}
    assert {"字节-后端", "算法专题"} <= categories


def test_algorithm_bank_loads_and_searches():
    import agent

    agent._QUESTION_CACHE = None
    try:
        bank = agent._load_question_bank()
        assert any(record.get("role") == "算法工程师" for record in bank)
        result = agent.search_questions.call(
            {"query": "反转链表", "role": "算法工程师", "limit": 3})
        assert "找到" in result
        assert "反转链表" in result
    finally:
        agent._QUESTION_CACHE = None