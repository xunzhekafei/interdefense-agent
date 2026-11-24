# -*- coding: utf-8 -*-
"""陈述单元：把答辩/汇报讲稿切成可引用的单元。

为什么需要单元切分
------------------
面试的追问对象是"候选人刚说的一句话"，所以现有运行时只需要看最近几轮对话；
答辩的追问对象是"讲稿里的某一段主张"——评委问的是"你第 2 部分说用了 XX 方法，
它的输入输出是什么"。没有稳定编号，追问就只能泛泛地问，报告里的证据也没法
回链到具体段落，"可检查、可修正"就落不了地。

因此这里做三件事：

1. 把讲稿切成带 ``U1/U2/...`` 编号、带 ``start/end`` 偏移的单元；
2. 提供把单元清单渲染进 system prompt 的文本；
3. 解析模型在问句里留下的 ``[[U3]]`` 标记，并把证据回链到单元。

偏移量是刻意保留的：单元文本必须能在用户提交的原文里原样定位，这样报告里的
引用和讲稿才能对得上。所有函数只做确定性处理，不调用模型，便于离线测试。
"""
import re

# 单元编号只允许 U + 数字；标记形如 [[U2]] 或 [[U2,U5]]。
UNIT_ID_RE = re.compile(r"^U\d+$")
_MARKER_RE = re.compile(r"\[\[\s*(U\d+(?:\s*[,，、]\s*U\d+)*)\s*\]\]", re.IGNORECASE)

# 答辩与课程汇报共用的五段结构。关键词取"最长命中"，避免「数据」把
# 「数据结果」误判成方法段。
SECTION_RULES = (
    ("背景", ("研究背景", "选题背景", "研究现状", "背景", "问题", "现状", "意义",
              "动机", "选题", "需求", "目标", "引言", "绪论")),
    ("方法", ("技术路线", "研究方法", "实施方案", "方法", "方案", "设计", "实现",
              "过程", "实验", "模型", "架构", "做法", "流程")),
    ("结果", ("实验结果", "数据结果", "结果", "效果", "验证", "评估", "性能",
              "准确率", "对比", "指标", "结论")),
    ("创新", ("个人工作", "我的工作", "改进点", "创新", "贡献", "亮点", "特色")),
    ("局限", ("改进方向", "改进空间", "局限", "不足", "展望", "未来", "后续", "风险")),
)

DEFAULT_SECTION = "背景"
MAX_UNITS = 24
MAX_UNIT_CHARS = 600
MIN_UNIT_CHARS = 10
PROMPT_HEAD_CHARS = 240
PROMPT_LIMIT_CHARS = 6000


def normalize_script(script) -> str:
    """统一换行符，让单元偏移与入库的讲稿逐字对应。"""
    return str(script or "").replace("\r\n", "\n").replace("\r", "\n")


def _section_of(text) -> str | None:
    sample = str(text or "")[:100]
    best = None
    for section, keywords in SECTION_RULES:
        for keyword in keywords:
            if keyword in sample and (best is None or len(keyword) > best[1]):
                best = (section, len(keyword))
    return best[0] if best else None


def _is_heading(line: str) -> bool:
    """识别 Markdown 标题与「一、」「1.」「（一）」这类中文小标题。

    要求整行较短且不以句号/分号结尾，避免把正文里的「2. 我们做了……」当成标题。
    """
    text = line.strip()
    if not text or len(text) > 40 or text.endswith(("。", "；", "，", "？", "！")):
        return False
    if text.startswith("#"):
        return True
    return bool(re.match(
        r"^(?:第[一二三四五六七八九十百]+[章节部分]"
        r"|[一二三四五六七八九十]+[、．.]"
        r"|\d{1,2}[、．)）]"
        r"|（[一二三四五六七八九十]+）)", text))


def _blocks(text):
    """按空行和标题行切块，返回 [(start, end, raw)]。"""
    blocks = []
    current = []
    current_start = None
    position = 0
    for line in text.splitlines(keepends=True):
        line_start = position
        position += len(line)
        if not line.strip():
            if current:
                blocks.append((current_start, line_start, "".join(current)))
                current = []
                current_start = None
            continue
        if _is_heading(line) and current:
            blocks.append((current_start, line_start, "".join(current)))
            current = []
            current_start = None
        if current_start is None:
            current_start = line_start
        current.append(line)
    if current:
        blocks.append((current_start, position, "".join(current)))
    return blocks


def _sentence_spans(raw: str, base: int):
    """按句号/分号/换行切句，返回 [(start, end)]；保留标点。"""
    spans = []
    start = 0
    for index, char in enumerate(raw):
        if char in "。！？；\n":
            spans.append((base + start, base + index + 1))
            start = index + 1
    if start < len(raw):
        spans.append((base + start, base + len(raw)))
    return spans


def _split_long(text, start, end, limit, section):
    """超长块按句子边界切；单句仍超限时硬切，保证每块不超过 limit。"""
    raw = text[start:end]
    if len(raw) <= limit:
        return [{"start": start, "end": end, "section": section}]
    units = []
    current_start = None
    current_end = None
    for span_start, span_end in _sentence_spans(raw, start):
        if span_end - span_start > limit:
            if current_start is not None:
                units.append({"start": current_start, "end": current_end, "section": section})
                current_start = None
            cursor = span_start
            while cursor < span_end:
                units.append({"start": cursor, "end": min(cursor + limit, span_end),
                              "section": section})
                cursor += limit
            continue
        if current_start is not None and span_end - current_start > limit:
            units.append({"start": current_start, "end": current_end, "section": section})
            current_start = None
        if current_start is None:
            current_start = span_start
        current_end = span_end
    if current_start is not None:
        units.append({"start": current_start, "end": current_end, "section": section})
    return units


def _merge_short(units, text):
    """过短单元并进前一个，避免「好的」「谢谢」这类碎片成为独立追问目标。"""
    merged = []
    for unit in units:
        body = text[unit["start"]:unit["end"]].strip()
        if not body:
            continue
        if len(body) < MIN_UNIT_CHARS and merged:
            merged[-1]["end"] = unit["end"]
            continue
        merged.append(dict(unit))
    return merged


def _limit(units, text, max_units):
    """单元过多时合并相邻单元，而不是丢弃——丢掉的内容就再也追不到了。"""
    while len(units) > max_units and len(units) > 1:
        target = None
        for index in range(len(units) - 1):
            if units[index]["section"] == units[index + 1]["section"]:
                target = index
                break
        if target is None:
            target = 0
        head, tail = units[target], units[target + 1]
        units[target:target + 2] = [{"start": head["start"], "end": tail["end"],
                                     "section": head["section"]}]
    return units


def segment(script, scene="defense", max_units=MAX_UNITS,
            max_chars=MAX_UNIT_CHARS) -> list:
    """把讲稿切成陈述单元。

    返回 ``[{"id": "U1", "section": "背景", "text": "原文", "start": 0, "end": 42}]``。
    ``text[start:end]`` 恒等于 ``text`` 字段，报告回链依赖这一点。
    """
    text = normalize_script(script)
    if not text.strip():
        return []
    section = DEFAULT_SECTION
    raw_units = []
    for start, end, block in _blocks(text):
        found = _section_of(block)
        if found:
            section = found
        raw_units.extend(_split_long(text, start, end, max_chars, section))
    units = _limit(_merge_short(raw_units, text), text, max_units)
    result = []
    for index, unit in enumerate(units, start=1):
        body = text[unit["start"]:unit["end"]]
        left = len(body) - len(body.lstrip())
        body = body.strip()
        if not body:
            continue
        result.append({"id": f"U{index}", "section": unit["section"], "text": body,
                       "start": unit["start"] + left, "end": unit["start"] + left + len(body)})
    return result


def render(units, limit_chars=PROMPT_LIMIT_CHARS) -> str:
    """把单元清单渲染进 system prompt；超长时截断，不撑爆上下文。"""
    if not units:
        return ""
    lines = ["【陈述单元（追问的定位依据；不要整段复述给候选人）】"]
    for unit in units:
        body = unit.get("text", "")
        if len(body) > PROMPT_HEAD_CHARS:
            body = body[:PROMPT_HEAD_CHARS] + "…"
        lines.append(f"{unit['id']}【{unit.get('section', '其他')}】{body}")
    lines.append("规则：某一问确实锚定某个单元时，在该句末尾加 [[U3]]；一句最多引用一个，"
                 "不得编造编号；没锚定就不要加标记。")
    return "\n".join(lines)[:limit_chars]


def split_markers(text):
    """剥离 ``[[U2]]`` 标记，返回 (干净文本, 去重后的单元编号列表)。"""
    raw = str(text or "")
    refs = []
    for match in _MARKER_RE.finditer(raw):
        for part in re.split(r"[,，、]", match.group(1)):
            unit_id = part.strip().upper()
            if unit_id and unit_id not in refs:
                refs.append(unit_id)
    clean = _MARKER_RE.sub("", raw)
    clean = re.sub(r"[ \t]+\n", "\n", clean)
    clean = re.sub(r"\n[ \t]+", "\n", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip(), refs


def resolve_refs(units, refs) -> list:
    """只保留真实存在的单元编号，防止模型编造 U99。"""
    known = {unit.get("id") for unit in units or []}
    resolved = []
    for ref in refs or []:
        unit_id = str(ref or "").strip().upper()
        if UNIT_ID_RE.match(unit_id) and unit_id in known and unit_id not in resolved:
            resolved.append(unit_id)
    return resolved


def _normalize(text) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def unit_of_quote(units, quote):
    """把一段证据原话回链到包含它的单元；找不到返回 None。"""
    target = _normalize(quote)
    if len(target) < 2:
        return None
    for unit in units or []:
        if target in _normalize(unit.get("text", "")):
            return unit.get("id")
    return None


def coverage(units, qa) -> dict:
    """统计每个陈述单元被追问了多少次、哪些一次都没被问到。"""
    counts = {}
    for item in qa or []:
        for ref in resolve_refs(units, item.get("unit_ref") or []):
            counts[ref] = counts.get(ref, 0) + 1
    rows = []
    for unit in units or []:
        refs = counts.get(unit.get("id"), 0)
        rows.append({"id": unit.get("id"), "section": unit.get("section"),
                     "text": unit.get("text"), "references": refs,
                     "covered": refs > 0})
    covered = [row for row in rows if row["covered"]]
    return {
        "total": len(rows),
        "covered": len(covered),
        "ratio": round(len(covered) / len(rows), 2) if rows else None,
        "units": rows,
        "uncovered": [row for row in rows if not row["covered"]],
    }