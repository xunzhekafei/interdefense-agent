# -*- coding: utf-8 -*-
"""把上传的讲稿文件提取成纯文本。

为什么放在服务端而不是浏览器里解析
--------------------------------
`.docx` / `.pptx` 是 zip + XML，浏览器端要引一个不小的解析库；而且同一份讲稿
在手机和电脑上解析结果必须一致。放在服务端只做一次解析，前端拿到的就是和
粘贴进来完全相同的文本，后面切分、回链、评分全都走同一条路。

安全边界
--------
上传文件是不可信输入：
- 按扩展名白名单，不认的格式直接拒绝（`.doc` / `.ppt` 旧二进制格式也拒绝，
  并提示另存为 `.docx`）；
- 读入前限大小，解析前检查 zip 里声明的解压后总大小与条目数，防 zip 炸弹；
- 不解压到磁盘、不执行任何内容，只在内存里解析；
- 提取出的文本限长（与 `SessionInput.script` 的上限一致），超了明确标记截断。

标题的处理
----------
Word 的「标题 1」样式、PPT 的幻灯片标题会转成 `## 标题`。陈述单元切分本来就
按 Markdown 标题分段，这样上传的讲稿和手写的讲稿得到同样的段落划分。
"""
import io
import re
import zipfile
from pathlib import Path

MAX_UPLOAD_BYTES = 10 * 1024 * 1024          # 单个文件上限
MAX_UNCOMPRESSED_BYTES = 60 * 1024 * 1024    # zip 解压后总大小上限
MAX_ZIP_ENTRIES = 500                        # zip 条目数上限
MAX_TEXT_CHARS = 20000                       # 与 SessionInput.script 的 max_length 一致

TEXT_SUFFIXES = (".txt", ".md", ".markdown")
SUPPORTED_SUFFIXES = (*TEXT_SUFFIXES, ".docx", ".pptx")
LEGACY_SUFFIXES = (".doc", ".ppt")

_KIND_LABELS = {".txt": "文本", ".md": "Markdown", ".markdown": "Markdown",
                ".docx": "Word", ".pptx": "PowerPoint"}


class ScriptImportError(ValueError):
    """带用户可读原因的导入失败。"""


def _clean_filename(filename: str) -> str:
    """只留文件名本体：客户端可以带任何路径，不能让它进日志或界面。"""
    name = Path(str(filename or "")).name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:120] or "未命名文件"


def _check_zip(data: bytes) -> None:
    """解析前先看 zip 的元数据，挡住声明了几百 MB 的压缩包。"""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile:
        raise ScriptImportError("文件已损坏，或不是有效的 Office 文档") from None
    if len(infos) > MAX_ZIP_ENTRIES:
        raise ScriptImportError("文档内部结构异常（文件过多），请重新导出后再试")
    total = sum(info.file_size for info in infos)
    if total > MAX_UNCOMPRESSED_BYTES:
        raise ScriptImportError("文档解压后体积过大，请只上传讲稿正文")
    if any(info.file_size > MAX_UNCOMPRESSED_BYTES for info in infos):
        raise ScriptImportError("文档内部有异常大的对象，请重新导出后再试")


def _decode_text(data: bytes) -> str:
    """中文讲稿常见 UTF-8、GBK、UTF-16（记事本「Unicode」）；依次尝试。

    UTF-16 必须靠 BOM 先判：文件头是 FF FE / FE FF 时，按 gb18030 解出来是乱码
    而不会报错，模型会拿到一堆「烫烫烫」。gb18030 放最后，它对字节最宽容。
    """
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ScriptImportError("无法识别文本编码，请另存为 UTF-8 编码的 .txt 后重试")


def _docx_text(data: bytes) -> str:
    _check_zip(data)
    try:
        import docx
        document = docx.Document(io.BytesIO(data))
    except ScriptImportError:
        raise
    except Exception:
        raise ScriptImportError("无法读取这个 Word 文档，请另存为 .docx 后重试") from None

    lines = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        # Word 的标题样式 → Markdown 标题，切分时才会当成段标题而不是正文
        style = str(getattr(paragraph.style, "name", "") or "")
        if text and style.lower().startswith(("heading", "标题")):
            text = "## " + text
        lines.append(text)
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _pptx_text(data: bytes) -> str:
    _check_zip(data)
    try:
        from pptx import Presentation
        deck = Presentation(io.BytesIO(data))
    except ScriptImportError:
        raise
    except Exception:
        raise ScriptImportError("无法读取这个 PPT 文档，请另存为 .pptx 后重试") from None

    blocks = []
    for index, slide in enumerate(deck.slides, start=1):
        title = ""
        shapes = getattr(slide.shapes, "title", None)
        if shapes is not None and getattr(shapes, "has_text_frame", False):
            title = shapes.text_frame.text.strip()
        body = []
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False):
                continue
            text = shape.text_frame.text.strip()
            if text and text != title:
                body.append(text)
        heading = f"## {title}" if title else f"## 第 {index} 页"
        blocks.append("\n".join([heading, *body]))
    return "\n\n".join(blocks)


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract(filename: str, data: bytes) -> dict:
    """返回 ``{text, filename, kind, chars, truncated}``；失败抛 ScriptImportError。

    提取结果是给用户**确认和编辑**的初稿，不是最终提交内容——前端会把它填进
    输入框，学生可以改；这样「AI 读错了我的讲稿」在开始追问之前就能发现。
    """
    name = _clean_filename(filename)
    suffix = Path(name).suffix.lower()

    if not data:
        raise ScriptImportError("文件是空的")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ScriptImportError(
            f"文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB，请只上传讲稿正文")
    if suffix in LEGACY_SUFFIXES:
        raise ScriptImportError(
            f"暂不支持旧版 .{suffix[1:]} 格式，请在 Office / WPS 里「另存为」.docx / .pptx 后再上传")
    if suffix == ".pdf":
        raise ScriptImportError(
            "暂不支持 PDF（排版复杂、提取顺序容易乱），请上传 .docx 或把文字复制进来")
    if suffix not in SUPPORTED_SUFFIXES:
        raise ScriptImportError("只支持 .docx / .pptx / .txt / .md 四种格式")

    if suffix in TEXT_SUFFIXES:
        raw = _decode_text(data)
    elif suffix == ".docx":
        raw = _docx_text(data)
    else:
        raw = _pptx_text(data)

    text = _normalize(raw)
    if not text:
        raise ScriptImportError("文件里没有提取到文字——如果是扫描件或图片，请改上传文字版")
    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS]
    return {
        "text": text,
        "filename": name,
        "kind": _KIND_LABELS.get(suffix, suffix.lstrip(".")),
        "chars": len(text),
        "truncated": truncated,
    }
