# -*- coding: utf-8 -*-
"""试用数据导出：匿名化、指标计算、两轮配对。纯函数，无外部依赖。"""
import json
import sqlite3

from tools.trial_export import (build_summary, labels_for, load_sessions,
                                pair_rounds, rows_for)


def _session(name, created, overall, dims, covered=2, total=4, asked=4, scored=3):
    return {
        "id": f"s-{name}-{created}",
        "candidate": name,
        "created_at": created,
        "scene": "defense",
        "rounds": 10,
        "messages": [{"role": "user", "text": f"A{i}", "status": "completed"}
                     for i in range(asked)],
        "report": {
            "overall": overall,
            "dimension_scores": dims,
            "per_question": [{"question": f"Q{i}"} for i in range(scored)],
            "skipped_questions": [{"question": "你好"}],
            "unit_coverage": {"covered": covered, "total": total,
                              "ratio": round(covered / total, 2)},
        },
    }


def test_labels_are_anonymous_by_default():
    sessions = [_session("张同学", "2026-11-01", 5, {}),
                _session("李同学", "2026-11-02", 6, {})]
    labels = labels_for(sessions, include_names=False)
    assert set(labels.values()) == {"P01", "P02"}
    assert "张同学" not in labels.values()

    named = labels_for(sessions, include_names=True)
    assert named["张同学"] == "张同学"


def test_rows_carry_explainable_metrics():
    rows = rows_for([_session("甲", "2026-11-01", 5.5, {"表达与应答": 6})],
                    {"甲": "P01"})
    row = rows[0]
    assert row["participant"] == "P01"
    assert row["answered"] == 4
    assert row["scored"] == 3
    assert row["skipped"] == 1
    assert row["coverage"] == 0.5
    assert row["overall"] == 5.5


def test_pair_rounds_computes_deltas():
    rows = rows_for([
        _session("甲", "2026-11-01T10:00", 5.0, {"表达与应答": 5, "方法与论证严谨性": 4}),
        _session("甲", "2026-11-03T10:00", 6.5, {"表达与应答": 7, "方法与论证严谨性": 6},
                 covered=3),
    ], {"甲": "P01"})
    pairs = pair_rounds(rows)

    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["overall_delta"] == 1.5
    assert pair["coverage_delta"] == 0.25
    assert pair["dims"]["表达与应答"]["delta"] == 2
    assert pair["dims"]["方法与论证严谨性"]["delta"] == 2


def test_single_session_participant_is_not_paired():
    rows = rows_for([_session("甲", "2026-11-01", 5, {}),
                     _session("乙", "2026-11-02", 6, {})], {"甲": "P01", "乙": "P02"})
    assert pair_rounds(rows) == []


def test_summary_states_it_is_not_a_controlled_trial():
    rows = rows_for([_session("甲", "2026-11-01", 5, {"表达与应答": 5}),
                     _session("甲", "2026-11-03", 6, {"表达与应答": 6})], {"甲": "P01"})
    text = build_summary(rows, pair_rounds(rows))
    assert "不是对照实验" in text
    assert "P01" in text
    assert "总分平均变化" in text


def test_load_sessions_reads_payload_and_report(tmp_path):
    db_path = tmp_path / "interviews.sqlite3"
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, payload TEXT, summary TEXT, report TEXT)")
    session = _session("甲", "2026-11-01", 5, {})
    db.execute("INSERT INTO sessions VALUES (?,?,?,?)",
               (session["id"], json.dumps(session, ensure_ascii=False), None,
                json.dumps(session["report"], ensure_ascii=False)))
    db.commit()
    db.close()

    loaded = load_sessions(db_path)
    assert len(loaded) == 1
    assert loaded[0]["candidate"] == "甲"
    assert loaded[0]["report"]["overall"] == 5


def test_missing_database_exits(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        load_sessions(tmp_path / "nope.sqlite3")
