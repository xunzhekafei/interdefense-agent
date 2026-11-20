"""新增岗位题库：结构、角色、来源与真实检索。"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "interview" / "data"

BANKS = [
    ("android_questions.json", "Android 工程师", 800),
    ("ios_questions.json", "iOS 工程师", 90),
    ("devops_questions.json", "DevOps 工程师", 150),
    ("product_questions.json", "产品经理", 80),
    ("data_engineering_questions.json", "数据工程师", 30),
    ("php_questions.json", "PHP 工程师", 140),
    ("node_questions.json", "Node.js 工程师", 110),
]


@pytest.mark.parametrize("filename,role,minimum", BANKS)
def test_role_bank_shape(filename, role, minimum):
    records = json.loads((DATA / filename).read_text(encoding="utf-8"))
    assert len(records) >= minimum
    assert all(record["role"] == role for record in records)
    assert len({record["question"] for record in records}) == len(records)
    assert all(record["question"].strip() for record in records)
    assert all(record["lang"] in ("zh", "en") for record in records)
    assert all(record["source"] for record in records)


def test_role_banks_load_and_search():
    import agent

    agent._QUESTION_CACHE = None
    try:
        bank = agent._load_question_bank()
        roles = {record.get("role") for record in bank}
        for _, role, _ in BANKS:
            assert role in roles

        assert "找到" in agent.search_questions.call(
            {"query": "ANR", "role": "Android 工程师", "limit": 3})
        assert "找到" in agent.search_questions.call(
            {"query": "PHP", "role": "PHP 工程师", "limit": 3})
        assert "找到" in agent.search_questions.call(
            {"query": "MLOps", "role": "数据工程师", "limit": 3})
    finally:
        agent._QUESTION_CACHE = None


def test_role_banks_source_document():
    text = (DATA / "ROLE_BANKS_SOURCE.md").read_text(encoding="utf-8")
    assert "Hacked" in text          # ios-cn 被黑，已记录为排除
    assert "Apache-2.0" in text
    assert "Unlicense" in text
    assert "CC0-1.0" in text