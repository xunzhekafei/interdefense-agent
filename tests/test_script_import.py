# -*- coding: utf-8 -*-
"""讲稿上传解析：格式、编码、标题转换与不可信输入防护。

全部离线，不调用模型。
"""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend import script_import
from backend.app import create_app
from backend.script_import import ScriptImportError, extract


def _docx_bytes(with_table=True):
    import docx
    document = docx.Document()
    document.add_heading("研究背景", level=1)
    document.add_paragraph("现有系统回答不了跨章节的问题。")
    document.add_paragraph("")
    document.add_heading("研究方法", level=1)
    document.add_paragraph("先用向量召回，再用重排模型。")
    if with_table:
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "指标"
        table.rows[0].cells[1].text = "81%"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pptx_bytes():
    from pptx import Presentation
    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])   # 标题和内容
    slide.shapes.title.text = "实验结果"
    slide.placeholders[1].text = "准确率从 62% 提升到 81%"
    buffer = io.BytesIO()
    deck.save(buffer)
    return buffer.getvalue()


# ---------- 文本 ----------

def test_txt_utf8():
    result = extract("讲稿.txt", "研究背景\n现有工具不够用。".encode("utf-8"))
    assert result["text"].startswith("研究背景")
    assert result["kind"] == "文本"
    assert result["truncated"] is False


def test_txt_gbk():
    """中文讲稿在 Windows 上另存为 ANSI 就是 GBK。"""
    result = extract("讲稿.txt", "研究背景\n现有工具不够用。".encode("gbk"))
    assert "现有工具不够用" in result["text"]


def test_txt_utf16_from_notepad():
    """Windows 记事本「Unicode」保存的是 UTF-16 LE，带 BOM。"""
    data = "研究背景\n现有工具不够用。".encode("utf-16")   # 自动带 BOM
    result = extract("讲稿.txt", data)
    assert "现有工具不够用" in result["text"]
    assert "�" not in result["text"]


def test_markdown_keeps_structure():
    text = "## 研究背景\n\n现有工具不够用。\n"
    result = extract("讲稿.md", text.encode("utf-8"))
    assert result["text"] == "## 研究背景\n\n现有工具不够用。"


# ---------- Word ----------

def test_docx_paragraphs_and_headings():
    result = extract("毕设讲稿.docx", _docx_bytes())
    assert result["kind"] == "Word"
    # Word 的标题样式要转成 Markdown 标题，切分时才按段标题处理
    assert "## 研究背景" in result["text"]
    assert "## 研究方法" in result["text"]
    assert "先用向量召回" in result["text"]


def test_docx_table_text_is_kept():
    result = extract("讲稿.docx", _docx_bytes(with_table=True))
    assert "指标 | 81%" in result["text"]


# ---------- PowerPoint ----------

def test_pptx_slides_become_sections():
    result = extract("答辩.pptx", _pptx_bytes())
    assert result["kind"] == "PowerPoint"
    assert "## 实验结果" in result["text"]
    assert "准确率从 62% 提升到 81%" in result["text"]


# ---------- 拒绝与防护 ----------

def test_legacy_doc_is_rejected_with_hint():
    with pytest.raises(ScriptImportError, match="另存为"):
        extract("旧讲稿.doc", b"anything")


def test_pdf_is_rejected_with_hint():
    with pytest.raises(ScriptImportError, match="暂不支持 PDF"):
        extract("讲稿.pdf", b"%PDF-1.4")


def test_unknown_suffix_is_rejected():
    with pytest.raises(ScriptImportError, match="只支持"):
        extract("讲稿.exe", b"MZ")


def test_empty_file_is_rejected():
    with pytest.raises(ScriptImportError, match="空的"):
        extract("讲稿.txt", b"")


def test_filename_path_is_stripped():
    """客户端可能带路径或控制字符，不能原样进界面。"""
    result = extract("../../etc/讲稿.txt", "正文内容".encode("utf-8"))
    assert result["filename"] == "讲稿.txt"


def test_corrupt_docx_is_rejected():
    with pytest.raises(ScriptImportError, match="损坏|无法读取"):
        extract("坏.docx", b"not a zip at all")


def test_zip_bomb_is_rejected(monkeypatch):
    """zip 里声明解压后超大 → 解析前就拒绝（这里用一份真实 docx 改小阈值来验证）。"""
    data = _docx_bytes()
    monkeypatch.setattr(script_import, "MAX_UNCOMPRESSED_BYTES", 10)
    with pytest.raises(ScriptImportError, match="体积过大"):
        extract("讲稿.docx", data)


def test_too_many_zip_entries_is_rejected(monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for index in range(5):
            archive.writestr(f"f{index}.xml", "x")
    monkeypatch.setattr(script_import, "MAX_ZIP_ENTRIES", 3)
    with pytest.raises(ScriptImportError, match="结构异常"):
        extract("讲稿.docx", buffer.getvalue())


def test_oversized_upload_is_rejected(monkeypatch):
    monkeypatch.setattr(script_import, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(ScriptImportError, match="超过"):
        extract("讲稿.txt", b"x" * 11)


def test_long_text_is_truncated_and_flagged(monkeypatch):
    monkeypatch.setattr(script_import, "MAX_TEXT_CHARS", 5)
    result = extract("讲稿.txt", "一二三四五六七八九十".encode("utf-8"))
    assert result["text"] == "一二三四五"
    assert result["truncated"] is True


# ---------- 路由 ----------

class FakeAgent:
    def configured(self):
        return True


def test_import_route_returns_text(tmp_path):
    with TestClient(create_app(tmp_path, FakeAgent(), recognizer=None)) as client:
        response = client.post(
            "/api/import-script",
            files={"file": ("讲稿.txt", "研究背景\n现有工具不够用。".encode("utf-8"), "text/plain")},
        )
        assert response.status_code == 200
        body = response.json()
        assert "现有工具不够用" in body["text"]
        assert body["filename"] == "讲稿.txt"


def test_import_route_rejects_legacy_format(tmp_path):
    with TestClient(create_app(tmp_path, FakeAgent(), recognizer=None)) as client:
        response = client.post("/api/import-script",
                               files={"file": ("旧讲稿.doc", b"xx", "application/msword")})
        assert response.status_code == 400
        assert "另存为" in response.json()["detail"]


def test_import_route_rejects_oversized_upload(tmp_path, monkeypatch):
    import backend.app as app_module
    monkeypatch.setattr(app_module, "SCRIPT_MAX_BYTES", 4)
    with TestClient(create_app(tmp_path, FakeAgent(), recognizer=None)) as client:
        response = client.post("/api/import-script",
                               files={"file": ("讲稿.txt", b"12345", "text/plain")})
        assert response.status_code == 413
