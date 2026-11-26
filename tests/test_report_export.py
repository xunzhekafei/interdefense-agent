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
    assert "综合评分：7.47" in markdown
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

def test_markdown_title_follows_scene():
    """答辩导出的标题不能还写「面试复盘报告」。"""
    assert "# 答辩复盘报告" in to_markdown(REPORT, "defense")
    assert "# 课程汇报复盘报告" in to_markdown(REPORT, "presentation")
    assert "# 面试复盘报告" in to_markdown(REPORT, "interview")


def test_markdown_without_overall_omits_score_line():
    """有效回答不足时没有总分，不能渲染成「综合评分：None」。"""
    markdown = to_markdown({"summary": "本次只完成 1 题。", "overall": None})
    assert "综合评分" not in markdown
    assert "本次只完成 1 题。" in markdown


def test_markdown_includes_unit_coverage_and_anchor():
    """导出的 PDF/Markdown 要能自证「问到哪、没问到哪」，不能只在网页里。"""
    report = {
        "overall": 3.5,
        "summary": "摘要",
        "dimension_scores": {"方法与论证严谨性": 3.5},
        "per_question": [{
            "question": "你说的 81% 是多少条数据上测的？",
            "evidence": "240 条",
            "suggestion": "补基线",
            "unit_ref": ["U3"],
            "方法与论证严谨性": 6,
        }],
        "units": [{"id": "U3", "section": "结果", "text": "准确率从 62% 提升到 81%。"}],
        "unit_coverage": {
            "total": 24, "covered": 1, "ratio": 0.04,
            "units": [], "uncovered": [{"id": f"U{i}"} for i in range(1, 24)],
        },
        "target_rounds": 15,
        "focus_checks": [{"text": "个人贡献", "checked": True}],
    }
    markdown = to_markdown(report, "defense")
    assert "## 陈述单元覆盖" in markdown
    assert "共 24 段，本场追问覆盖 1 段（4%）" in markdown
    assert "等 23 段" in markdown
    assert "覆盖不全属正常" in markdown
    assert "> 锚定讲稿：U3【结果】准确率从 62% 提升到 81%。" in markdown
    assert "- [已检验] 个人贡献" in markdown
