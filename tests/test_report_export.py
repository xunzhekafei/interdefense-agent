from backend.report_export import to_markdown, to_pdf

REPORT = {
    "overall": 7.47,
    "summary": "整体回答结构清晰，技术细节还可以再展开。",
    "dimension_scores": {"技术正确性": 8.25, "深度与原理": 6.13},
    "strengths": ["基础概念准确"],
    "weaknesses": ["缺少公式推导"],
    "recommendations": ["补充离线与线上指标映射"],
    "per_question": [
        {
            "question": "Dropout 在训练和推理阶段有什么区别？",
            "evidence": "训练时随机失活，推理时缩放",
            "suggestion": "可以补一句 inverted dropout 的缩放位置。",
            "evidence_verified": True,
            "技术正确性": 8.5,
            "深度与原理": 6.0,
        }
    ],
    "skipped_questions": [
        {
            "question": "你好",
            "answer": "",
            "reason": "greeting",
            "reason_text": "问候不计分",
        }
    ],
}


def test_markdown_contains_core_sections():
    markdown = to_markdown(REPORT)
    assert "# 面试复盘报告" in markdown
    assert "综合评分：7.5" in markdown
    assert "技术正确性" in markdown
    assert "逐题复盘" in markdown
    assert "证据：" in markdown
    assert "未计分的轮次" in markdown
    assert "（空）" in markdown


def test_markdown_handles_empty_report():
    markdown = to_markdown({})
    assert "# 面试复盘报告" in markdown
    assert "生成时间：" in markdown


def test_pdf_is_valid_and_not_empty():
    data = to_pdf(REPORT)
    assert data.startswith(b"%PDF")
    assert len(data) > 1000


def test_pdf_handles_empty_report():
    data = to_pdf({})
    assert data.startswith(b"%PDF")
    assert len(data) > 500