"""面试报告的 Markdown / PDF 导出。

只做渲染，不调用模型；输入是会话里的 report 字典。
"""
from __future__ import annotations

import html
from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

FONT = "STSong-Light"
_font_ready = False


def _ensure_font() -> None:
    global _font_ready
    if not _font_ready:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT))
        _font_ready = True


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _score(value: Any) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return _text(value) or "—"


def _esc(value: Any) -> str:
    return html.escape(_text(value)).replace("\n", "<br/>")


def to_markdown(report: dict) -> str:
    lines: list[str] = ["# 面试复盘报告", ""]
    overall = report.get("overall")
    if overall is not None:
        lines += [f"**综合评分：{_score(overall)} / 10**", ""]
    summary = report.get("summary")
    if summary:
        lines += [_text(summary).strip(), ""]

    dimensions = report.get("dimension_scores") or {}
    if dimensions:
        lines += ["## 维度得分", ""]
        for name, value in dimensions.items():
            lines.append(f"- {name}：{_score(value)} / 10")
        lines.append("")

    for heading, key in (
        ("你的优势", "strengths"),
        ("值得加强", "weaknesses"),
        ("下一步练习", "recommendations"),
    ):
        items = report.get(key) or []
        if not items:
            continue
        lines += [f"## {heading}", ""]
        lines += [f"- {item}" for item in items]
        lines.append("")

    per_question = report.get("per_question") or []
    if per_question:
        lines += ["## 逐题复盘", ""]
        for index, item in enumerate(per_question, 1):
            lines.append(f"### {index:02d}. {_text(item.get('question')).strip()}")
            lines.append("")
            for name in dimensions:
                if name in item:
                    lines.append(f"- {name}：{_score(item[name])}")
            evidence = item.get("evidence")
            if evidence:
                lines += ["", f"> 证据：{evidence}"]
                if item.get("evidence_verified") is False:
                    lines += [
                        ">",
                        "> 这条证据未通过原话校验，可能是模型改写或概括的，仅供参考。",
                    ]
            suggestion = item.get("suggestion")
            if suggestion:
                lines += ["", str(suggestion)]
            lines.append("")

    skipped = report.get("skipped_questions") or []
    if skipped:
        lines += [
            "## 未计分的轮次",
            "",
            "这些轮次没有有效作答（误触、问候、跳过或反问），已从均分中剔除，不影响综合评分。",
            "",
        ]
        for index, item in enumerate(skipped, 1):
            lines.append(f"### {index:02d}. {_text(item.get('question')).strip()}")
            lines.append("")
            answer = _text(item.get("answer")).strip() or "（空）"
            lines.append(f"> 回答：{answer}")
            lines.append("")
            lines.append(_text(item.get("reason_text") or item.get("reason")))
            lines.append("")

    lines += ["---", f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"]
    return "\n".join(lines).rstrip() + "\n"


def to_pdf(report: dict) -> bytes:
    _ensure_font()
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="面试复盘报告",
        author="Interview Studio",
    )

    base = getSampleStyleSheet()
    title = ParagraphStyle(
        "title", parent=base["Title"], fontName=FONT, fontSize=18, leading=24, spaceAfter=8
    )
    heading2 = ParagraphStyle(
        "heading2",
        parent=base["Heading2"],
        fontName=FONT,
        fontSize=13,
        leading=18,
        spaceBefore=10,
        spaceAfter=5,
    )
    heading3 = ParagraphStyle(
        "heading3",
        parent=base["Heading3"],
        fontName=FONT,
        fontSize=11,
        leading=16,
        spaceBefore=8,
        spaceAfter=3,
    )
    body = ParagraphStyle(
        "body", parent=base["BodyText"], fontName=FONT, fontSize=10.5, leading=16, spaceAfter=5
    )
    quote = ParagraphStyle(
        "quote",
        parent=body,
        fontSize=9.5,
        leading=15,
        leftIndent=10,
        textColor=HexColor("#555555"),
    )
    small = ParagraphStyle(
        "small", parent=body, fontSize=8.5, leading=12, textColor=HexColor("#777777")
    )

    story: list[Any] = [Paragraph("面试复盘报告", title)]
    overall = report.get("overall")
    if overall is not None:
        story.append(Paragraph(f"综合评分：<b>{_score(overall)}</b> / 10", body))
    summary = report.get("summary")
    if summary:
        story.append(Paragraph(_esc(summary), body))

    dimensions = report.get("dimension_scores") or {}
    if dimensions:
        story.append(Paragraph("维度得分", heading2))
        for name, value in dimensions.items():
            story.append(Paragraph(f"{_esc(name)}：{_score(value)} / 10", body))

    for heading, key in (
        ("你的优势", "strengths"),
        ("值得加强", "weaknesses"),
        ("下一步练习", "recommendations"),
    ):
        items = report.get(key) or []
        if not items:
            continue
        story.append(Paragraph(heading, heading2))
        for item in items:
            story.append(Paragraph(f"• {_esc(item)}", body))

    per_question = report.get("per_question") or []
    if per_question:
        story.append(Paragraph("逐题复盘", heading2))
        for index, item in enumerate(per_question, 1):
            story.append(Paragraph(f"{index:02d}. {_esc(item.get('question'))}", heading3))
            scores = [f"{_esc(name)}：{_score(item[name])}" for name in dimensions if name in item]
            if scores:
                story.append(Paragraph("　".join(scores), small))
            evidence = item.get("evidence")
            if evidence:
                story.append(Paragraph(f"证据：{_esc(evidence)}", quote))
                if item.get("evidence_verified") is False:
                    story.append(
                        Paragraph("这条证据未通过原话校验，可能是模型改写或概括的，仅供参考。", small)
                    )
            suggestion = item.get("suggestion")
            if suggestion:
                story.append(Paragraph(_esc(suggestion), body))

    skipped = report.get("skipped_questions") or []
    if skipped:
        story.append(Paragraph("未计分的轮次", heading2))
        story.append(
            Paragraph("这些轮次没有有效作答，已从均分中剔除，不影响综合评分。", small)
        )
        for index, item in enumerate(skipped, 1):
            story.append(Paragraph(f"{index:02d}. {_esc(item.get('question'))}", heading3))
            answer = _esc(item.get("answer")) or "（空）"
            story.append(Paragraph(f"回答：{answer}", quote))
            story.append(Paragraph(_esc(item.get("reason_text") or item.get("reason")), small))

    story.append(Spacer(1, 8))
    story.append(Paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", small))
    document.build(story)
    return output.getvalue()