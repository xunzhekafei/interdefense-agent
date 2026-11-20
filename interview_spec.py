# -*- coding: utf-8 -*-
"""面试评分口径的单一来源。

维度名、权重、评分版本只在这里定义一次：
- agent.py 的评分 workflow 从这里读
- backend/profile.py 的跨场次聚合从这里读
- 前端不硬编码维度名——报告和逐题事件里带的是 dimension_scores 的键

改这里的任何一项（维度、权重、分制）都必须同时递增 SCORING_VERSION，
否则成长曲线会把「口径变了」误画成「水平变了」。
"""

import re

# v1：只有 0-10 的整数要求
# v2：加入分档标尺
# v3：总分由「四维均分」改为「按权重加权和」
# v4：重复题目、问候、空回答、主动跳过和反问环节不计分，避免误触拉低总分
SCORING_VERSION = 4

DIMENSIONS = (
    ("技术正确性", 0.30),
    ("深度与原理", 0.30),
    ("工程与场景思考", 0.25),
    ("表达与结构", 0.15),
)

DIMENSION_NAMES = tuple(name for name, _ in DIMENSIONS)
DIMENSION_WEIGHTS = dict(DIMENSIONS)


def weighted_overall(scores: dict) -> float | None:
    """按权重算总分；缺维度时用已有维度的权重重新归一化。

    未考察的维度不应该按 0 分拉低总分——这和 backend-interview-simulator
    的阶段性综合分是同一条规则。
    """
    total = 0.0
    weight_sum = 0.0
    for name, weight in DIMENSIONS:
        value = scores.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            total += float(value) * weight
            weight_sum += weight
    if weight_sum == 0:
        return None
    return round(total / weight_sum, 2)


# ---------------- 轮数计划 ----------------

ROUND_OPTIONS = (10, 15, 20, 30, 50)
DEFAULT_ROUNDS = 15
# 去掉开场自我介绍和反问后，剩余题目按这个比例分配
ROUND_MIX = (("项目深挖", 0.40), ("技术基础", 0.30), ("系统设计", 0.20), ("行为协作", 0.10))

# 岗位不同，考察重心也不同：前端多问项目与工程，AI 多问原理，
# 数据岗多问指标与协作。未识别的岗位沿用通用比例，行为与旧版完全一致。
ROLE_MIXES = {
    "frontend": (("项目深挖", 0.45), ("技术基础", 0.25), ("系统设计", 0.20), ("行为协作", 0.10)),
    "ai": (("项目深挖", 0.40), ("技术基础", 0.35), ("系统设计", 0.15), ("行为协作", 0.10)),
    "data": (("项目深挖", 0.35), ("技术基础", 0.25), ("系统设计", 0.20), ("行为协作", 0.20)),
    "backend": (("项目深挖", 0.35), ("技术基础", 0.30), ("系统设计", 0.25), ("行为协作", 0.10)),
}


def role_mix(role: str):
    """按岗位关键词挑题目配比；识别不了就用通用配比。"""
    text = str(role or "").lower()
    if any(word in text for word in ("前端", "frontend", "web")):
        return ROLE_MIXES["frontend"]
    if any(word in text for word in ("ai", "ml", "算法", "机器学习", "人工智能")):
        return ROLE_MIXES["ai"]
    if any(word in text for word in ("数据", "data", "分析")):
        return ROLE_MIXES["data"]
    if any(word in text for word in ("后端", "backend", "服务端")):
        return ROLE_MIXES["backend"]
    return ROUND_MIX


def round_plan(rounds: int, role: str = "") -> dict:
    """把总轮数拆成各类题目的配额；总题数包含开场和反问。

    返回 {"rounds": 15, "intro": 1, "project": 5, "technical": 4,
          "design": 3, "behavior": 1, "reverse": 1}

    `role` 只影响配额，不影响总数；默认空串保持旧版通用比例。
    """
    rounds = rounds if rounds in ROUND_OPTIONS else DEFAULT_ROUNDS
    mix = role_mix(role)
    core = max(1, rounds - 2)                 # 去掉开场和反问
    plan = {"rounds": rounds, "intro": 1, "reverse": 1}
    allocated = 0
    for index, (name, weight) in enumerate(mix):
        if index == len(mix) - 1:
            count = max(0, core - allocated)  # 最后一项吃掉四舍五入的余数
        else:
            count = max(0, round(core * weight))
            allocated += count
            if allocated > core:              # 各项四舍五入可能超额，削掉多出来的
                count -= allocated - core
                allocated = core
        plan[{"项目深挖": "project", "技术基础": "technical",
              "系统设计": "design", "行为协作": "behavior"}[name]] = count
    return plan


# ---------------- 无效作答识别 ----------------

_REVERSE_MARKERS = ("有什么想问我的", "有什么问题要问我", "想问我什么", "有问题问我")
_GREETING_RE = re.compile(
    r"^(你好|您好|hi|hello|嗨|在吗|嗯+|哦+|好的|好吧|行|可以|谢谢|thanks|thankyou|ok|okay)$")
_SKIP_RE = re.compile(r"^(跳过|下一题|pass|skip|不答了)$")
_PUNCT_RE = re.compile(r"[\W_]+", re.UNICODE)


def _normalize(text: str) -> str:
    return _PUNCT_RE.sub("", str(text or "")).lower()


def is_reverse_question(question: str) -> bool:
    q = _normalize(question)
    return any(marker in q for marker in _REVERSE_MARKERS)


def classify_answer(question: str, answer: str) -> str:
    """判断一轮问答该不该计分。

    返回：
      score     正常回答，计分
      reverse   反问环节，不计分
      copy      回答与问题几乎相同（误触/复制题目）
      greeting  只有问候或语气词
      empty     空回答
      skip      候选人主动跳过
    """
    if is_reverse_question(question):
        return "reverse"
    q = _normalize(question)
    a = _normalize(answer)
    if not a:
        return "empty"
    if a == q:
        return "copy"
    # 把题目整段抄回来（允许少量前后缀），但回答明显更长时不算
    if len(q) >= 8 and q in a and len(a) <= len(q) * 1.25:
        return "copy"
    if len(a) <= 8 and _GREETING_RE.match(a):
        return "greeting"
    if _SKIP_RE.match(a):
        return "skip"
    return "score"


SKIP_REASONS = {
    "reverse": "反问环节，不计入评分",
    "copy": "回答与问题几乎相同，疑似误触或复制题目",
    "greeting": "只有问候/语气词，没有实际作答",
    "empty": "空回答",
    "skip": "候选人主动跳过",
}
