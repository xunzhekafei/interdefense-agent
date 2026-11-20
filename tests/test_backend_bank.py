"""后端题库：结构、许可标注与真实检索。"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "interview" / "data" / "backend_questions.json"


def test_backend_bank_shape():
    records = json.loads(BANK.read_text(encoding="utf-8"))
    assert len(records) >= 400
    assert len({record["question"] for record in records}) == len(records)
    assert all(record["role"] == "后端开发工程师" for record in records)
    assert all(record["question"].strip() for record in records)
    assert all(record["lang"] == "zh" for record in records)
    assert all("MIT" in record["source"] for record in records)

    categories = Counter(record["category"] for record in records)
    assert {"Go", "MySQL", "Python", "Redis", "网络", "系统编程"} <= set(categories)


def test_backend_bank_loads_and_searches():
    import agent

    agent._QUESTION_CACHE = None
    try:
        bank = agent._load_question_bank()
        backend = [record for record in bank if record.get("role") == "后端开发工程师"]
        assert len(backend) >= 400

        result = agent.search_questions.call(
            {"query": "Redis 持久化", "role": "后端开发工程师", "limit": 5})
        assert "找到" in result
        assert "Redis" in result
    finally:
        agent._QUESTION_CACHE = None


def test_backend_sources_are_documented():
    text = (ROOT / "interview" / "data" / "BACKEND_SOURCE.md").read_text(encoding="utf-8")
    assert "yongxinz/backend-interview" in text
    assert "MIT" in text
    assert "492" in text