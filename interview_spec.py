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
# v5：维度按场景分开——答辩/汇报不再套用面试四维
SCORING_VERSION = 5

# 少于这个题数不产出四维评分。
# 一道题答得好不好，说明不了「答辩水平」；硬打四个维度分，等于把一次回答的
# 表现当成整体能力，报告越长越像真的，反而误导。此时只保留逐题反馈。
MIN_SCORED_ROUNDS = 3

# 求职面试：评估的是「这个人能不能干这份工作」
DIMENSIONS = (
    ("技术正确性", 0.30),
    ("深度与原理", 0.30),
    ("工程与场景思考", 0.25),
    ("表达与结构", 0.15),
)

DIMENSION_NAMES = tuple(name for name, _ in DIMENSIONS)
DIMENSION_WEIGHTS = dict(DIMENSIONS)

# 答辩 / 课程汇报：评估的是「这份工作本身站不站得住、是不是他做的」。
# 用面试四维去套，报告会写「技术正确性 4 分」，而答辩现场关心的是
# 工作量、论证、个人贡献——这正是「面试换皮」最容易被识破的地方。
DEFENSE_DIMENSIONS = (
    ("方法与论证严谨性", 0.35),
    ("工作量与完整性", 0.25),
    ("创新与个人贡献", 0.25),
    ("表达与应答", 0.15),
)
DEFENSE_DIMENSION_NAMES = tuple(name for name, _ in DEFENSE_DIMENSIONS)

SCENE_DIMENSIONS = {
    "interview": DIMENSIONS,
    "defense": DEFENSE_DIMENSIONS,
    "presentation": DEFENSE_DIMENSIONS,
}


def dimensions_for(scene: str = "") -> tuple:
    """场景 → 维度与权重；未知场景按求职面试处理（与改造前行为一致）。"""
    return SCENE_DIMENSIONS.get(str(scene or "interview"), DIMENSIONS)


def dimension_names(scene: str = "") -> tuple:
    return tuple(name for name, _ in dimensions_for(scene))


def all_dimension_names() -> tuple:
    """所有场景的维度并集，按场景顺序去重。跨场景画像用它遍历。"""
    names = []
    for dims in SCENE_DIMENSIONS.values():
        for name, _ in dims:
            if name not in names:
                names.append(name)
    return tuple(names)


# 每个维度「评什么」——写进逐题评分的 prompt。只写维度名而不写判断依据，
# 模型会把四个维度打成差不多的分（实测四维之间相关系数偏高）。
RUBRICS = {
    "interview": {
        "技术正确性": "事实、结论、术语是否正确，有无明显错误或过时说法",
        "深度与原理": "是否讲清「为什么」，能否解释机制、取舍与代价，而不是只报结果",
        "工程与场景思考": "边界、失败路径、可复现性、真实约束下能不能用",
        "表达与结构": "是否先给结论再展开，条理清楚、重点突出",
    },
    "defense": {
        "方法与论证严谨性": "主张是否有证据支撑；基线、样本量、统计口径是否交代；"
                          "因果与相关是否分清；对反例和替代解释有没有回应",
        "工作量与完整性": "背景、方法、结果、创新、局限是否讲全；关键环节是真的做了，"
                        "还是只有设想；工作量与成果是否匹配",
        "创新与个人贡献": "创新点是否具体、与已有工作的差异是否说清；"
                         "本人承担的部分能否与团队工作区分，有没有把别人的工作说成自己的",
        "表达与应答": "陈述是否结构化；被追问时是否正面回答，有没有答非所问、转移话题或回避",
    },
}

# 分档标尺：没有锚点时同一回答的分数会漂（std 0.31），加档位后降到 0.15。
BANDS = {
    "interview": (
        ("9-10", "结论正确，讲清原理与取舍，主动给出量化证据和边界；追问能接住"),
        ("7-8", "结论正确，原理基本清楚，有一定证据，但细节或边界有缺口"),
        ("5-6", "方向对，但停留在表面或复述定义，缺少个人实践与证据"),
        ("3-4", "有明显错误或空洞表述，几乎没有可验证的信息"),
        ("0-2", "核心概念错误，或基本没有回答"),
    ),
    "defense": (
        ("9-10", "论证有完整证据链（基线、样本、口径齐全），个人贡献清楚，"
                 "追问能正面接住并主动说明边界"),
        ("7-8", "主张基本有证据，个别口径或边界没交代，追问基本接得住"),
        ("5-6", "讲了做法和结果，但证据停在结论层，追问时回避或答非所问"),
        ("3-4", "只有设想或复述，缺少可验证证据，多处答非所问"),
        ("0-2", "陈述空洞或事实错误，基本没有实质内容"),
    ),
}


def rubric_for(scene: str = "") -> dict:
    return RUBRICS.get(str(scene or "interview"), RUBRICS["interview"])


def bands_for(scene: str = "") -> tuple:
    return BANDS.get(str(scene or "interview"), BANDS["interview"])


def weighted_overall(scores: dict, dims=None) -> float | None:
    """按权重算总分；缺维度时用已有维度的权重重新归一化。

    未考察的维度不应该按 0 分拉低总分——这和 backend-interview-simulator
    的阶段性综合分是同一条规则。``dims`` 不传时按求职面试四维算（旧调用方行为不变）。
    """
    dims = DIMENSIONS if dims is None else dims
    total = 0.0
    weight_sum = 0.0
    for name, weight in dims:
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
