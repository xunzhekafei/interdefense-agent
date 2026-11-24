# -*- coding: utf-8 -*-
"""摘要卡：把陈述单元整理成学生可确认、可修正的理解清单。

为什么需要摘要卡
----------------
只把追问锚定到单元还不够。学生得先确认"AI 理解的是不是我要说的"：
如果理解错了，追问越精准反而越偏。摘要卡就是这个确认点，同时把学生修正过的
理解沉淀成下一场的检验点，形成"可检查、可修正"的闭环。

数据形态（存放在 session["summary_card"]）
----------------------------------------
{
  "version": 1,
  "claims": [{"id": "C1", "unit_ref": "U2", "text": "...",
              "status": "pending|confirmed|rejected", "edited_text": null}],
  "open_questions": [{"id": "Q1", "unit_ref": "U3", "text": "...",
                      "status": "pending|resolved|dismissed"}],
  "confirmed": false,
  "confirmed_at": null
}

所有函数只做确定性处理；模型输出先经 ``normalize`` 校验，不合法就退回规则生成，
因此模型不可用时摘要卡仍然能出来。
"""
import json
import re

CARD_VERSION = 1
MAX_CLAIMS = 8
MAX_QUESTIONS = 6
MAX_FOCUS = 5

CLAIM_STATUSES = ("pending", "confirmed", "rejected")
QUESTION_STATUSES = ("pending", "resolved", "dismissed")

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|％|倍|万|千|条|人|个|次|天|小时|分|秒)")
_EVIDENCE_WORDS = ("基线", "对比", "样本", "数据集", "数据来源", "口径",
                   "显著性", "置信", "p<", "p＝", "p=")
_VALIDATION_WORDS = ("验证", "实验", "测试", "评估", "测量")
_NOVELTY_WORDS = ("相比", "已有", "相关工作", "最接近", "基线", "baseline")
_METHOD_WORDS = ("输入", "输出", "步骤", "流程", "预处理", "训练", "推理", "实现")


def _clip(text, limit):
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _normalize(text):
    return re.sub(r"\s+", "", str(text or ""))


def _first_sentence(text, limit=120):
    body = str(text or "").strip()
    if not body:
        return ""
    # 单元通常以 Markdown 标题开头；标题不是"主张"，先剥掉再取正文第一句。
    body = re.sub(r"^\s*#{1,6}[^\n]*\n?", "", body, count=1).strip()
    if not body:
        return ""
    match = re.search(r"[。！？；\n]", body)
    sentence = body[:match.end()] if match else body
    return _clip(sentence, limit)


def rule_claims(units):
    """规则兜底：每段取第一句作为"AI 理解到的核心主张"。"""
    claims = []
    for unit in units or []:
        text = _first_sentence(unit.get("text"), 120)
        if not text:
            continue
        claims.append({"id": f"C{len(claims) + 1}", "unit_ref": unit.get("id"),
                       "text": text, "status": "pending", "edited_text": None})
        if len(claims) >= MAX_CLAIMS:
            break
    return claims


def _question_for(unit_text):
    """按"这段最可能被追问什么"生成一条待补充点；文本不命中规则就返回 None。"""
    if _NUMBER_RE.search(unit_text) and not any(word in unit_text for word in _EVIDENCE_WORDS):
        return "这一段的数字缺少基线、样本量或统计口径。"
    if (("提升" in unit_text or "提高" in unit_text or "优于" in unit_text)
            and not any(word in unit_text for word in _VALIDATION_WORDS)):
        return "这个提升是用什么实验或数据验证的？"
    if (("创新" in unit_text or "首次" in unit_text or "提出" in unit_text)
            and not any(word in unit_text for word in _NOVELTY_WORDS)):
        return "创新点与最接近的已有工作相比，差异在哪里？"
    if (("方法" in unit_text or "模型" in unit_text or "算法" in unit_text)
            and not any(word in unit_text for word in _METHOD_WORDS)):
        return "方法的输入、输出与关键步骤是什么？"
    return None


def rule_questions(units):
    questions = []
    for unit in units or []:
        text = str(unit.get("text") or "")
        question = _question_for(text)
        if not question:
            continue
        questions.append({"id": f"Q{len(questions) + 1}", "unit_ref": unit.get("id"),
                          "text": question, "status": "pending"})
        if len(questions) >= MAX_QUESTIONS:
            break
    return questions


def normalize(raw, units):
    """校验模型输出：只保留真实存在的单元引用与非空文本，编号由我们重排。"""
    known = {unit.get("id") for unit in units or []}
    if not isinstance(raw, dict):
        return [], []
    claims = []
    for item in raw.get("claims") or []:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("unit_id") or item.get("unit_ref") or "").strip().upper()
        text = _clip(item.get("text"), 160)
        if ref in known and text:
            claims.append({"id": f"C{len(claims) + 1}", "unit_ref": ref,
                           "text": text, "status": "pending", "edited_text": None})
        if len(claims) >= MAX_CLAIMS:
            break
    questions = []
    for item in raw.get("open_questions") or []:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("unit_id") or item.get("unit_ref") or "").strip().upper()
        text = _clip(item.get("text"), 160)
        if ref in known and text:
            questions.append({"id": f"Q{len(questions) + 1}", "unit_ref": ref,
                              "text": text, "status": "pending"})
        if len(questions) >= MAX_QUESTIONS:
            break
    return claims, questions


def build_card(units, raw=None):
    """优先用模型结果；缺项、伪造编号、全部为空时退回规则生成。

    ``source`` 明确告诉用户这张卡是模型概括的还是规则兜底的——不能让人以为
    所有措辞都来自模型。
    """
    claims, questions = normalize(raw, units)
    from_model = bool(claims)
    if not claims:
        claims = rule_claims(units)
    if not questions:
        questions = rule_questions(units)
    return {"version": CARD_VERSION, "source": "model" if from_model else "rules",
            "claims": claims, "open_questions": questions,
            "confirmed": False, "confirmed_at": None}


def _apply(entries, edits, statuses):
    allowed = {item.get("id"): item for item in entries}
    for edit in edits or []:
        if not isinstance(edit, dict):
            continue
        target = allowed.get(str(edit.get("id") or ""))
        if target is None:
            continue
        status = str(edit.get("status") or "").strip()
        if status in statuses:
            target["status"] = status
        if status != "rejected":
            text = _clip(edit.get("edited_text"), 200) if edit.get("edited_text") else ""
            if text:
                target["edited_text"] = text


def apply_edits(card, claims=None, open_questions=None):
    """应用学生的逐条修正；只接受白名单状态，未知 id 静默忽略。"""
    updated = json.loads(json.dumps(card, ensure_ascii=False))
    _apply(updated.get("claims") or [], claims, CLAIM_STATUSES)
    _apply(updated.get("open_questions") or [], open_questions, QUESTION_STATUSES)
    return updated


def confirm(card):
    """一键确认：pending 的主张全部转为 confirmed；被驳回的保持 rejected。"""
    updated = json.loads(json.dumps(card, ensure_ascii=False))
    for claim in updated.get("claims") or []:
        if claim.get("status") == "pending":
            claim["status"] = "confirmed"
    updated["confirmed"] = True
    return updated


def focus_items(card, units, limit=MAX_FOCUS):
    """下一场要检验的点：已确认的主张 + 未被否掉的待补充问题。

    ``quote`` 保存该单元原文开头，下一场讲稿重新切分后仍能靠它找回同一段。
    """
    by_id = {unit.get("id"): unit for unit in units or []}
    items = []
    for claim in card.get("claims") or []:
        if claim.get("status") != "confirmed":
            continue
        text = _clip(claim.get("edited_text") or claim.get("text"), 120)
        if not text:
            continue
        unit = by_id.get(claim.get("unit_ref")) or {}
        items.append({"kind": "claim", "id": claim.get("id"), "text": text,
                      "quote": _clip(unit.get("text"), 80),
                      "unit_ref": claim.get("unit_ref")})
    for question in card.get("open_questions") or []:
        if question.get("status") == "dismissed":
            continue
        text = _clip(question.get("text"), 120)
        if not text:
            continue
        unit = by_id.get(question.get("unit_ref")) or {}
        items.append({"kind": "question", "id": question.get("id"), "text": text,
                      "quote": _clip(unit.get("text"), 80),
                      "unit_ref": question.get("unit_ref")})
    return items[:limit]


def focus_checks(focus, turns):
    """报告用：判断上一场的检验点这一场有没有真的被追问到。

    用单元原文前 16 个字符做锚，而不是精确匹配整句——追问会改写措辞，
    但"回指同一段"的用词通常还在。
    """
    checks = []
    corpora = [_normalize((turn.get("question") or "") + (turn.get("answer") or ""))
               for turn in turns or []]
    for item in focus or []:
        needle = _normalize(item.get("quote") or item.get("text"))[:16]
        checked = bool(needle) and any(needle in body for body in corpora)
        checks.append({**item, "checked": checked})
    return checks