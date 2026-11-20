# -*- coding: utf-8 -*-
"""长面试评测的公共实现。

四个入口脚本：
    long_interview_10.py / long_interview_15.py / long_interview_20.py / long_interview_30.py

每个入口固定轮数；默认从新增岗位里选 3 个，各跑 2 场。
回答模板每个岗位 30 条，30 轮不会循环复用，避免“面试官指出候选人反复复述”。
"""
import argparse
import json
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from role_diff_eval import HINTS, message  # noqa: E402

ROLES = ["数据工程师", "DevOps 工程师", "产品经理"]

ANSWERS = {
    "数据工程师": [
        "我负责过数据平台的一部分，从业务库抽数到数仓，也做过实时和离线两条链路，日常和算法、分析师、运维协作。",
        "增量同步主要用 binlog 加时间戳兜底，遇到 schema 变更会先兼容字段再切流，失败任务支持断点续跑。",
        "迟到和乱序数据按事件时间加水位处理，超过窗口的数据进补偿队列，第二天再合并到分区。",
        "重跑幂等靠分区覆盖加唯一键去重，任务先写临时分区，校验通过后再原子切换。",
        "数据质量用非空、枚举、分布和环比规则，异常时先阻断下游并告警，人工确认后再放行。",
        "数仓分 ODS、DWD、DWS 三层，DWD 做明细清洗和维度关联，DWS 做主题聚合，边界按使用方和更新频率划分。",
        "维度建模以事实表和维度表为主，宽表按查询场景收敛，避免一张表承接所有需求。",
        "调度用 Airflow，任务有依赖、重试和 SLA；关键链路会提前跑，失败时先看依赖和资源。",
        "实时和离线按延迟要求选型，分钟级用流式，T+1 用批处理；两边共用同一套指标定义。",
        "特征一致性靠统一特征定义和同一份离线/实时计算逻辑，上线前做样本对齐校验。",
        "模型部署流水线包含训练、评估、打包、灰度、回滚，模型版本和特征版本一起记录。",
        "存储成本按分区、压缩和生命周期控制，冷数据下沉，热数据保留短周期。",
        "数据血缘记录表到表、字段到字段的关系，变更影响分析时先查下游。",
        "权限按最小可见原则，敏感字段脱敏，审计日志保留，跨域访问需要审批。",
        "压测会看峰值吞吐、延迟和资源水位，提前给调度和存储留余量。",
        "故障处理先停任务或切备链路，再定位是数据、依赖还是资源问题，恢复后补数据。",
        "和算法协作会先定数据契约，包括字段、口径、刷新频率和缺失处理。",
        "监控覆盖任务成功率、延迟、数据量和质量规则，告警按影响面分级。",
        "复盘会看根因、发现时间和恢复时间，最后落到规则、监控或流程改动。",
        "我的问题：团队现在的数据平台规模和主要技术栈是怎样的？",
        "元数据管理会维护表、字段、指标口径和负责人，做变更评审时先看影响范围。",
        "实时链路出现背压时，会先看消费延迟和分区倾斜，再限流、扩容或降级非核心数据。",
        "历史数据回刷先评估下游影响和资源窗口，分批跑并做抽样校验，避免一次性打满集群。",
        "值班时按影响面分级，先止损再定位，重大故障会同步业务方和负责人。",
        "存储选型会在湖、仓和对象存储之间权衡，重点看查询模式、成本和数据治理需求。",
        "数据安全会做分级分类，敏感数据脱敏，访问走审批和审计，定期检查权限。",
        "跨团队需求先评审价值和成本，不合理的需求会带着替代方案退回去。",
        "数据故障复盘会输出时间线、影响范围、根因和可执行的改进项。",
        "技术趋势上我关注流批一体和湖仓，但会先看团队现状和迁移成本。",
        "我的问题：团队现在最想优先解决的数据问题是什么？",
    ],
    "DevOps 工程师": [
        "我负责过 Linux 服务器、CI/CD 和 Kubernetes 运维，日常和开发、测试、安全团队协作。",
        "Linux 排障会先看负载、内存、磁盘和网络，再用 top、iostat、ss、tcpdump 逐层定位。",
        "Kubernetes 发布用 Deployment 加探针和滚动更新，资源限制和 HPA 按压测结果配置。",
        "CI/CD 流水线包含构建、单测、镜像、安全扫描和灰度发布，失败会阻断后续阶段。",
        "镜像安全会做基础镜像收敛、依赖扫描和签名校验，禁止直接使用 latest。",
        "监控用 Prometheus 加 Grafana，告警按 SLO 配置，区分症状告警和原因告警。",
        "SLO 会定义分子分母和统计窗口，错误预算用于判断是否暂停发布。",
        "DNS 排查会区分解析失败和连接失败，常用 dig、nslookup、curl 和抓包。",
        "发布策略有滚动、蓝绿和灰度，数据库变更会拆成兼容的前后两步。",
        "回滚要保证镜像、配置和数据库都能退，回滚脚本会定期演练。",
        "容量规划结合历史峰值和压测，设置资源 requests/limits 和扩容阈值。",
        "备份会做定期恢复演练，验证恢复时间和数据一致性。",
        "基础设施用 Terraform 管理，环境差异通过变量隔离，减少手工漂移。",
        "密钥放在 Secret 管理系统，按最小权限分发，定期轮换并审计使用。",
        "故障演练会模拟节点宕机、网络分区和依赖超时，验证降级和切换。",
        "成本优化看资源利用率和闲置实例，做集群合并和弹性伸缩。",
        "和开发协作会明确发布准入、回滚责任和 on-call 边界。",
        "权限按角色和环境隔离，生产变更需要审批和双人确认。",
        "复盘会看 MTTR、变更失败率和告警噪音，最后落到自动化或流程改动。",
        "我的问题：团队现在的发布频率和 on-call 机制是怎样的？",
        "Linux 参数调优会关注文件句柄、TIME_WAIT 和内核网络参数，但先确认瓶颈再改。",
        "容器网络会排查 Service、Ingress、DNS 和 NetworkPolicy，区分集群内和集群外问题。",
        "证书和域名会做到期监控和自动续期，避免因为证书过期导致全站不可用。",
        "变更管理会控制发布窗口、审批和回滚预案，高风险变更要求双人复核。",
        "SLO 错误预算用完后会暂停新功能发布，优先做稳定性和技术债。",
        "混沌工程会从只读、低风险场景开始，逐步验证依赖超时和节点故障。",
        "云成本治理会做资源标签、闲置回收和弹性伸缩，定期 review 异常账单。",
        "多集群和灾备会明确 RPO/RTO，定期演练切换，避免只有方案没有验证。",
        "事故复盘会区分直接原因和系统性原因，改进项要有负责人和截止时间。",
        "我的问题：团队现在最头疼的稳定性问题是什么？",
    ],
    "产品经理": [
        "我负责过一个 AI 助手功能，先明确用户任务和边界，再写 PRD，和算法、设计、研发一起落地。",
        "需求边界会先写清系统能做什么、不能做什么，以及失败时用户看到什么。",
        "指标用一个北极星加若干过程指标，避免只看单一准确率。",
        "PRD 里会写输入输出、失败处理、人工兜底、隐私合规和验收标准。",
        "评估集会做小规模 gold set，按用户切片看覆盖，不只看总体分数。",
        "灰度会设置小流量、观察指标和停止条件，出问题能快速回退。",
        "成本会算推理、存储和人工审核，给单次任务设预算上限。",
        "人机交互要明确哪些动作自动、哪些必须人工确认，尤其是不可逆操作。",
        "失败兜底包括拒答、转人工、提示重试和降级到规则方案。",
        "隐私合规会做数据最小化、脱敏、保留期限和用户授权。",
        "优先级按用户影响、实现成本和风险综合评估，不做纯演示型功能。",
        "跨团队协作会先对齐目标和约束，再用试验结果做决策。",
        "竞品分析关注用户任务和失败场景，不只对比功能列表。",
        "上线计划包含灰度范围、监控指标、客服话术和回滚预案。",
        "上线后看采纳率、任务完成率、错误率和人工修改率。",
        "复盘会区分产品问题、模型问题和运营问题，分别落到不同改进项。",
        "商业化会考虑付费意愿、成本结构和合规边界。",
        "路线图按验证假设排序，先做能证伪核心风险的小实验。",
        "风险清单包括模型漂移、数据泄露、错误建议和供应商依赖。",
        "我的问题：团队现在如何衡量 AI 功能的成功？",
        "用户研究会先看真实任务和现有替代方案，不急着问“你想要什么功能”。",
        "需求评审会明确不做清单和上线门槛，砍需求时给出替代方案。",
        "指标异常会先区分数据问题、产品问题和外部因素，再做归因。",
        "A/B 实验会先定假设、样本量和停止条件，避免看到显著就放大。",
        "合规评议会提前拉法务和安全，明确数据边界和用户告知。",
        "模型和供应商选型会看能力、成本、稳定性和退出成本，避免单点依赖。",
        "跨团队资源争取会用目标和数据说话，明确优先级和交付边界。",
        "季度路线图会留出探索和稳定性预算，避免排满交付型需求。",
        "功能下线会提前做用户沟通、迁移方案和数据保留策略。",
        "我的问题：团队现在产品、算法和工程的协作方式是怎样的？",
    ],
}


def now():
    return datetime.now(timezone.utc).isoformat()


def is_reverse(question: str) -> bool:
    return "有什么想问" in question or "想问我" in question or "问我" in question


def run_session(agent_cls, role: str, session_index: int, turns: int, output_dir: Path):
    session = {
        "id": f"long-{role}-{session_index}",
        "candidate": "评估候选人",
        "role": role,
        "background": "5 年相关经验，做过中等规模项目。",
        "pressure": "标准",
        "rounds": turns,
        "messages": [],
        "memory": None,
        "memory_version": 0,
    }
    agent = agent_cls()
    questions, errors = [], []
    answers = ANSWERS[role]
    for turn in range(turns):
        turn_id = uuid.uuid4().hex
        cancel = threading.Event()
        events = []

        def emit(event_type, data):
            events.append((event_type, data))

        text, last_error = "", None
        for attempt in range(3):
            events.clear()
            try:
                text = agent.reply(session, emit, cancel, output_dir / session["id"])
                text = re.sub(r"\s+", " ", text or "").strip()
                if not text:
                    text = "".join(
                        str(data.get("text", "")) for kind, data in events
                        if kind == "reply.delta").strip()
                if text:
                    break
                last_error = ValueError("模型返回空文本")
            except Exception as error:
                last_error = error
                time.sleep(2 + attempt * 3)
        if not text:
            cause = repr(getattr(last_error, "__cause__", None))
            errors.append({"turn": turn + 1,
                           "error": type(last_error).__name__ if last_error else "EmptyReply",
                           "message": (str(last_error)[:160] + " | cause=" + cause)[:300]})
            break
        questions.append(text)
        session["messages"].append(message(turn_id, "assistant", text))
        answer = answers[turn % len(answers)]
        session["messages"].append(message(turn_id, "user", f"第 {turn + 1} 轮补充：{answer}"))
        time.sleep(0.5)
    return {"role": role, "session": session_index, "questions": questions, "errors": errors}


BEHAVIOR_PEOPLE = ("团队", "同事", "上级", "leader", "新人", "跨团队", "开发", "算法",
                   "运维", "合作方", "双方", "对方", "负责人")
BEHAVIOR_SITUATIONS = ("分歧", "意见不一致", "冲突", "争执", "僵持", "反对", "被采纳",
                       "说服", "沟通", "带人", "管理", "责任", "值班", "资源争取",
                       "怎么推进", "如何推进", "怎么推动", "协调")
INTRO_HINTS = ("自我介绍", "简历", "工作经历", "过往", "项目", "哪一块", "亲手", "负责",
               "业务场景", "体量", "背景", "角色", "团队规模")
CASE_HINTS = ("讲一次", "举一个", "举个例子", "案例", "后来", "事后", "复盘", "失误",
              "被证明", "失败", "判断对了吗", "对还是错", "影响产品方向", "教训",
              "根本原因", "取舍", "决策", "推翻")


def is_behavior(question: str) -> bool:
    """必须同时出现「人」和「人际情境」，避免「管理/团队/冲突」这类泛词误判。"""
    return (any(word in question for word in BEHAVIOR_PEOPLE)
            and any(word in question for word in BEHAVIOR_SITUATIONS))


def is_intro_or_project(question: str) -> bool:
    return any(word in question for word in INTRO_HINTS)


def is_case_or_judgment(question: str) -> bool:
    return any(word in question for word in CASE_HINTS)


def classify(question: str, hints) -> str:
    if is_behavior(question):
        return "behavior"
    if any(hint in question.lower() for hint in hints):
        return "technical"
    if is_case_or_judgment(question):
        return "case"
    if is_intro_or_project(question):
        return "intro"
    return "technical"          # 未命中词表的技术题，保留在技术题里供人工校正


def analyze(rows, roles):
    report = {}
    for role in roles:
        role_rows = [row for row in rows if row["role"] == role]
        questions = [q for row in role_rows for q in row["questions"] if not is_reverse(q)]
        hints = HINTS[role]
        behavior = [q for q in questions if classify(q, hints) == "behavior"]
        intro = [q for q in questions if classify(q, hints) == "intro"]
        case = [q for q in questions if classify(q, hints) == "case"]
        technical = [q for q in questions if classify(q, hints) == "technical"]
        normalized = [re.sub(r"[\s\W_]+", "", q.lower()) for q in questions]
        unique = len(set(normalized))

        def hit_rate(items):
            if not items:
                return 0.0
            return sum(any(hint in q.lower() for hint in hints) for q in items) / len(items)

        size = max(1, len(technical) // 3)
        sections = [technical[:size], technical[size:size * 2], technical[size * 2:]]

        counts = {}
        for question in questions:
            key = re.sub(r"[\s\W_]+", "", question.lower())
            counts[key] = counts.get(key, 0) + 1
        duplicates = []
        for question in questions:
            key = re.sub(r"[\s\W_]+", "", question.lower())
            if counts.get(key, 0) > 1 and question not in duplicates:
                duplicates.append(question)

        report[role] = {
            "sessions": len(role_rows),
            "questions": len(questions),
            "intro": len(intro),
            "technical": len(technical),
            "behavior": len(behavior),
            "case": len(case),
            "behavior_rate": round(len(behavior) / len(questions), 3) if questions else 0.0,
            "unique": unique,
            "repeat_rate": 0.0 if not normalized else 1 - unique / len(normalized),
            "first_hit": round(hit_rate(sections[0]), 3),
            "middle_hit": round(hit_rate(sections[1]), 3),
            "last_hit": round(hit_rate(sections[2]), 3),
            "duplicates": duplicates[:5],
            "samples": technical[:4] + behavior[:2],
            "behavior_samples": behavior[:5],
            "case_samples": case[:5],
            "unmatched_technical": [
                question for question in technical
                if not any(hint in question.lower() for hint in hints)][:5],
            "errors": sum(len(row["errors"]) for row in role_rows),
        }
    return report


def write_markdown(report, path: Path, sessions: int, turns: int, roles):
    lines = [f"# 长面试评测（{len(roles)} 个岗位 × {sessions} 场 × {turns} 轮）", "",
             "命中率只统计技术题；开场/项目、行为/协作、判断/案例题单独计数。", "",
             "| 岗位 | 场次 | 非反问 | 开场/项目 | 技术题 | 行为/协作 | 判断/案例 | 行为占比 | 唯一题 | 重复率 | 前段命中 | 中段命中 | 后段命中 | 错误 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for role in roles:
        data = report[role]
        lines.append(f"| {role} | {data['sessions']} | {data['questions']} | {data['intro']} | "
                     f"{data['technical']} | {data['behavior']} | {data['case']} | "
                     f"{data['behavior_rate']:.0%} | {data['unique']} | {data['repeat_rate']:.0%} | "
                     f"{data['first_hit']:.0%} | {data['middle_hit']:.0%} | "
                     f"{data['last_hit']:.0%} | {data['errors']} |")
    lines += ["", "## 重复问句", ""]
    for role in roles:
        lines.append(f"### {role}")
        duplicates = report[role]["duplicates"]
        if duplicates:
            for question in duplicates:
                lines.append(f"- {question}")
        else:
            lines.append("- 无逐字重复")
        lines.append("")
    lines += ["## 题目样例（技术题优先，含少量行为题）", ""]
    for role in roles:
        lines.append(f"### {role}")
        for question in report[role]["samples"]:
            lines.append(f"- {question}")
        lines.append("")
    lines += ["## 行为/协作题样例（用于校正行为题识别规则）", ""]
    for role in roles:
        lines.append(f"### {role}")
        samples = report[role]["behavior_samples"]
        if samples:
            for question in samples:
                lines.append(f"- {question}")
        else:
            lines.append("- 无")
        lines.append("")
    lines += ["## 判断/案例题样例（用于校正识别规则）", ""]
    for role in roles:
        lines.append(f"### {role}")
        samples = report[role]["case_samples"]
        if samples:
            for question in samples:
                lines.append(f"- {question}")
        else:
            lines.append("- 无")
        lines.append("")
    lines += ["## 未命中关键词的技术题样例（用于校正 HINTS）", ""]
    for role in roles:
        lines.append(f"### {role}")
        samples = report[role]["unmatched_technical"]
        if samples:
            for question in samples:
                lines.append(f"- {question}")
        else:
            lines.append("- 无")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(turns: int, sessions: int = 2, output: str | None = None, allow_turns: bool = False):
    parser = argparse.ArgumentParser()
    parser.add_argument("--roles", default=",".join(ROLES))
    parser.add_argument("--sessions", type=int, default=sessions)
    parser.add_argument("--output", default=None)
    if allow_turns:
        parser.add_argument("--turns", type=int, default=turns)
    args = parser.parse_args()
    effective_turns = args.turns if allow_turns else turns
    roles = [role.strip() for role in args.roles.split(",") if role.strip()]
    output_dir = Path(args.output or output or f"evals/results/long_{effective_turns}")
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "raw.jsonl"

    rows = []
    if raw_path.exists():
        rows = [json.loads(line) for line in raw_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    done = {(row["role"], row["session"]) for row in rows}

    from backend.agent_adapter import InterviewAgent

    for role in roles:
        for index in range(1, args.sessions + 1):
            if (role, index) in done:
                continue
            started = time.perf_counter()
            row = run_session(InterviewAgent, role, index, effective_turns, output_dir)
            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)
            elapsed = time.perf_counter() - started
            print(f"{role} 第 {index}/{args.sessions} 场：{len(row['questions'])}/{effective_turns} 轮，"
                  f"{elapsed:.1f}s，错误 {len(row['errors'])}", flush=True)

    report = analyze(rows, roles)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, output_dir / "report.md", args.sessions, effective_turns, roles)
    print("报告：", output_dir / "report.md", flush=True)