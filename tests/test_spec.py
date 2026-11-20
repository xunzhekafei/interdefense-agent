"""评分口径的单一来源：维度、权重、版本只定义一次。"""
import agent
import backend.profile as profile
import interview_spec as spec


def test_weights_sum_to_one():
    assert round(sum(spec.DIMENSION_WEIGHTS.values()), 6) == 1.0


def test_weighted_overall():
    scores = {"技术正确性": 8, "深度与原理": 7, "工程与场景思考": 6, "表达与结构": 9}
    assert spec.weighted_overall(scores) == 7.35


def test_weighted_overall_renormalizes_missing_dimensions():
    """未考察的维度不按 0 分拉低总分，而是用已有维度的权重重新归一化。"""
    assert spec.weighted_overall({"技术正确性": 8, "深度与原理": 6}) == 7.0


def test_agent_uses_the_shared_dimensions():
    assert agent.INTERVIEW_SCORE_DIMENSIONS == spec.DIMENSION_NAMES


def test_profile_uses_the_shared_dimensions():
    assert profile.DIMENSION_NAMES == spec.DIMENSION_NAMES


def test_round_plan_sums_to_target():
    for rounds in spec.ROUND_OPTIONS:
        plan = spec.round_plan(rounds)
        total = (plan["intro"] + plan["reverse"] + plan["project"]
                 + plan["technical"] + plan["design"] + plan["behavior"])
        assert total == rounds
        assert plan["project"] >= plan["technical"] >= plan["design"] >= plan["behavior"] >= 0


def test_round_plan_default_unchanged():
    """未识别岗位时必须保持旧比例，避免升级后悄悄改变题库分配。"""
    assert spec.round_plan(10) == {
        "rounds": 10, "intro": 1, "reverse": 1,
        "project": 3, "technical": 2, "design": 2, "behavior": 1}


def test_round_plan_varies_by_role():
    """岗位不同，配比不同；但总数始终等于目标轮数，且项目仍占最大头。"""
    default = spec.round_plan(15)
    frontend = spec.round_plan(15, "前端开发工程师")
    ai = spec.round_plan(15, "AI / ML 工程师")
    data = spec.round_plan(15, "数据分析师")

    assert frontend["project"] > default["project"]
    assert ai["technical"] > default["technical"]
    assert data["behavior"] >= default["behavior"]
    assert ai["technical"] >= ai["design"]

    for role in ("前端开发工程师", "AI / ML 工程师", "数据分析师",
                 "后端开发工程师", "未知岗位"):
        for rounds in spec.ROUND_OPTIONS:
            plan = spec.round_plan(rounds, role)
            total = (plan["intro"] + plan["reverse"] + plan["project"]
                     + plan["technical"] + plan["design"] + plan["behavior"])
            assert total == rounds
            assert plan["project"] >= plan["technical"] >= plan["design"] >= plan["behavior"] >= 0


def test_classify_answer_filters_accidents():
    assert spec.classify_answer("请做自我介绍", "请做自我介绍") == "copy"
    assert spec.classify_answer("请做自我介绍", "你好？") == "greeting"
    assert spec.classify_answer("请做自我介绍", "   ") == "empty"
    assert spec.classify_answer("请做自我介绍", "跳过") == "skip"
    assert spec.classify_answer("你有什么想问我的吗？", "你好") == "reverse"
    assert spec.classify_answer("什么是闭包？", "闭包是函数和其词法环境的组合") == "score"


def test_scoring_version_marks_invalid_answer_change():
    assert spec.SCORING_VERSION == 4
