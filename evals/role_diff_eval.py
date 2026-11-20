# -*- coding: utf-8 -*-
"""岗位差异化评测：每个岗位跑若干场 10 轮面试，统计题目差异。

    python evals/role_diff_eval.py --sessions 8 --turns 10
    python evals/role_diff_eval.py --roles "PHP 工程师" --sessions 1 --turns 2

只调用对话，不生成评分报告，成本可控。结果按场次增量写入 JSONL，
中断后用同样的命令会跳过已完成的场次。
"""
import argparse
import json
import re
import sys
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# 从 evals/ 目录直接运行时，项目根不在 sys.path，补上。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ROLES = [
    "Android 工程师",
    "iOS 工程师",
    "DevOps 工程师",
    "产品经理",
    "数据工程师",
    "PHP 工程师",
    "Node.js 工程师",
]

ANSWERS = {
    "Android 工程师": [
        "我在最近的项目里负责 Android 客户端，主要处理 Activity/Fragment 生命周期和 ANR 问题。有一次线上崩溃率升高，我通过日志和 StrictMode 定位到主线程 IO。",
        "长列表用的是 RecyclerView，滑动卡顿主要来自图片解码和过度绘制。我们做了分页预加载、图片采样和局部刷新，帧率稳定了很多。",
        "内存方面我排查过 Bitmap 泄漏和 Handler 持有 Activity 的问题，用 LeakCanary 定位后用静态内部类和弱引用修复。",
        "网络层我们封装了 OkHttp 拦截器，统一处理重试、缓存和登录态。也做过弱网下的超时与降级。",
        "我参与过组件化拆分，把业务模块独立成 AAR，通过路由解耦，构建时间从十几分钟降到几分钟。",
        "团队协作上我和后端约定接口契约，用 Mock 并行开发；出问题先看监控和埋点，再定位是客户端还是服务端。",
        "性能优化时我们先做基线采集，再用 Systrace/Perfetto 找瓶颈，最后用线上指标验证收益。",
        "我做过一段时间的稳定性专项，建立了崩溃聚合、ANR 归因和灰度回滚流程。",
        "如果重来一次，我会更早引入自动化测试和性能卡点，而不是等版本后期再补。",
        "我的问题：团队现在的发版节奏和灰度策略是怎样的？",
    ],
    "iOS 工程师": [
        "我主要负责 iOS 客户端，日常用 Swift 和 UIKit。最近做过一个复杂列表页面，用 UITableView 复用和预取优化滚动。",
        "Auto Layout 方面我处理过约束冲突和性能问题，复杂单元格会减少嵌套并用固定高度缓存。",
        "内存管理上排查过循环引用和闭包持有 self 的问题，用 weak/unowned 和 Instruments 定位。",
        "网络层用 URLSession 封装，处理过认证刷新、重试和取消；也做过离线缓存。",
        "架构上我们按模块拆分，用依赖注入和协议隔离，方便替换实现和写测试。",
        "线上崩溃通过符号化日志和崩溃聚合分析，修复后加灰度观察。",
        "性能优化会先看启动耗时、首帧和滚动帧率，再用 Instruments 找热点。",
        "我和设计、后端协作较多，接口变更会先对齐字段和错误码。",
        "后续我想补上更完整的 UI 自动化测试，减少回归成本。",
        "我的问题：团队对 SwiftUI 的采用程度如何？",
    ],
    "DevOps 工程师": [
        "我负责过 Linux 服务器运维和 CI/CD。最近把部署从脚本改成流水线，包含构建、测试、镜像和安全扫描。",
        "Kubernetes 方面我维护过 Deployment/Service/Ingress，处理过滚动更新失败和资源不足的问题。",
        "监控用 Prometheus + Grafana，告警按 SLO 配置；故障时先看指标和日志，再回滚。",
        "网络排查会从 DNS、连接、证书、负载均衡逐层定位，常用 dig、curl、tcpdump。",
        "权限和密钥通过 Secret 管理和最小权限控制，定期轮换。",
        "容量规划会结合历史峰值和压测结果，设置 HPA 和资源限制。",
        "我推动过基础设施即代码，环境用 Terraform 管理，减少手工漂移。",
        "备份和恢复演练是定期做的，重点验证恢复时间和数据一致性。",
        "如果重来一次，我会更早把可观测性和回滚流程标准化。",
        "我的问题：团队目前的发布频率和 on-call 机制是怎样的？",
    ],
    "产品经理": [
        "我负责过一个 AI 助手功能，先明确用户任务和边界，再做 PRD。第一版只做草稿生成，不自动发送。",
        "指标上我们看任务完成率、采纳率和人工修改率，同时监控错误率，不用单一准确率代替。",
        "做评估时建立了小规模 gold set，人工标注并按切片看覆盖，避免只看总体分数。",
        "和算法团队协作时，我会先定义失败场景和降级方案，再讨论模型选型。",
        "上线前做灰度和小流量实验，设置停止条件；上线后看用户反馈和成本。",
        "需求优先级用影响面和实现成本评估，避免为了演示效果堆功能。",
        "我写过 AI PRD，重点写清输入输出、失败处理、人工兜底和隐私合规。",
        "和设计协作时关注人机交互，明确系统能做什么、不能做什么。",
        "如果重来一次，我会更早把评估集和监控指标定下来。",
        "我的问题：团队现在如何衡量 AI 功能的成功？",
    ],
    "数据工程师": [
        "我负责过数据管道，从业务库抽取到数仓，处理增量同步、迟到数据和幂等。",
        "MLOps 方面我搭过特征计算和模型部署流水线，关注可复现和回滚。",
        "数据质量用规则校验和血缘追踪，异常时阻断下游并告警。",
        "存储上按分层建模，ODS/DWD/DWS，控制分区和生命周期。",
        "调度用 Airflow，任务有重试和 SLA；失败时先看依赖和资源。",
        "特征一致性是重点，训练和线上用同一套特征定义。",
        "成本优化会看存储和计算热点，做分区裁剪和压缩。",
        "和算法协作时明确数据契约、版本和刷新频率，避免训练线上不一致。",
        "如果重来一次，我会更早建立数据契约和质量门禁。",
        "我的问题：团队现在的数据平台和调度体系是怎样的？",
    ],
    "PHP 工程师": [
        "我做过 PHP 后端，主要用 Laravel。最近负责订单服务，处理过并发下单和幂等。",
        "MySQL 方面做过索引优化和慢查询治理，避免在索引列上做函数运算。",
        "Redis 用来做缓存和分布式锁，处理过缓存穿透和锁续期问题。",
        "接口设计上统一了错误码和参数校验，减少前后端联调成本。",
        "高并发场景用队列削峰，消息失败进入重试和死信。",
        "线上问题通过日志和链路追踪定位，先止损再复盘。",
        "我参与过服务拆分，把单体里的订单模块独立出来，明确边界。",
        "测试上补了接口集成测试和关键路径回归。",
        "如果重来一次，我会更早做压测和容量评估。",
        "我的问题：团队现在的 PHP 版本和服务化程度如何？",
    ],
    "Node.js 工程师": [
        "我做过 Node.js 后端，主要用 Express。最近负责一个 API 网关，处理鉴权、限流和转发。",
        "Event Loop 方面排查过同步阻塞导致的延迟，用异步 IO 和 worker 解决。",
        "回调地狱通过 async/await 和统一错误处理改造，接口可读性好了很多。",
        "数据库用 MongoDB/MySQL，处理过连接池、索引和事务边界。",
        "高并发下用集群和负载均衡，配合 Redis 做缓存和限流。",
        "线上问题通过日志、trace 和压测复现，先回滚再定位。",
        "我也写过 Go 服务，做过 Node 到 Go 的迁移评估，关注并发模型和生态。",
        "测试上补了接口测试和关键路径的压测脚本。",
        "如果重来一次，我会更早统一错误处理和可观测性。",
        "我的问题：团队现在的 Node 版本和部署方式是怎样的？",
    ],
}

HINTS = {
    "Android 工程师": ("anr", "activity", "fragment", "handler", "recyclerview", "内存", "性能",
                    "binder", "卡顿", "崩溃", "帧率", "主线程", "泄漏", "生命周期", "布局", "复用",
                    "looper", "渲染", "启动优化", "绘制"),
    "iOS 工程师": ("uikit", "autolayout", "arc", "swift", "tableview", "table view", "内存", "启动",
                "崩溃", "布局", "滚动", "帧率", "复用", "预取", "渲染", "自动布局", "weak",
                "unowned", "runloop", "gcd", "线程"),
    "DevOps 工程师": ("linux", "kubernetes", "k8s", "docker", "ci", "流水线", "监控", "告警", "dns",
                  "网络", "备份", "扩容", "镜像", "滚动更新", "容量", "故障", "slo", "secret", "terraform",
                  "load average", "crashloopbackoff", "pending", "oomkilled", "hpa", "qps",
                  "ingress", "service", "pod", "deployment", "kubectl", "df -h", "文件句柄",
                  "证书", "chaos", "灾备", "rpo", "rto", "变更", "发布", "回滚", "错误预算",
                  "etcd", "ping", "多集群", "多地", "签名", "节点", "容器", "网络策略",
                  "备份恢复", "数据库变更", "灰度", "容量规划", "混沌",
                  "区域", "切换", "容灾", "配额", "隔离", "自动化", "脚本", "多团队"),
    "产品经理": ("指标", "prd", "eval", "评估", "用户", "需求", "灰度", "准确率", "成本", "交互",
             "采纳率", "口径", "切片", "边界", "实验", "监控", "北极星", "质量分", "兜底",
             "gold set", "prompt", "mvp", "下线", "合规", "用户研究", "a/b", "路线图", "供应商",
             "rag", "微调", "检索", "政策", "agent", "自主", "归因", "异常", "离线评估",
             "抽样", "标注", "错误率", "成功率", "诊所", "第一版", "覆盖", "场景"),
    "数据工程师": ("pipeline", "mlops", "特征", "数据质量", "调度", "数仓", "血缘", "增量", "一致性",
              "幂等", "分区", "同步", "存储", "binlog", "upsert", "回刷", "重算", "重跑",
              "水位", "批处理", "流式", "实时", "离线", "去重", "延迟", "口径", "管道",
              "回滚", "故障", "权限", "脱敏", "t+1", "dwd", "dws", "原子切换", "校验",
              "环比", "大屏", "倾斜", "热键", "sla", "join", "元数据", "全量",
              "质量规则", "补数据", "架构评审", "单点", "宽表", "字段", "提前量",
              "配额", "隔离", "区域", "切换", "容灾"),
    "PHP 工程师": ("php", "laravel", "mysql", "redis", "索引", "队列", "并发", "缓存", "事务",
               "超卖", "锁", "幂等", "接口", "b+树", "双写", "短链", "限流", "分页", "慢查询"),
    "Node.js 工程师": ("node", "express", "event loop", "回调", "异步", "mongodb", "集群", "限流",
                   "gateway", "网关", "worker", "连接池", "流", "stream", "cluster", "socket", "压测"),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def message(turn_id, role, text):
    return {"id": uuid.uuid4().hex, "turn_id": turn_id, "role": role, "text": text,
            "status": "completed", "input_mode": "text", "created_at": now()}


def normalize(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", text.lower())


def token_set(text: str) -> set:
    words = set(re.findall(r"[a-z0-9]{2,}", text.lower()))
    chinese = {text[i:i + 2] for i in range(len(text) - 1)
               if "\u4e00" <= text[i] <= "\u9fff" and "\u4e00" <= text[i + 1] <= "\u9fff"}
    return words | chinese


def is_reverse(question: str) -> bool:
    return "有什么想问" in question or "想问我" in question or "问我" in question


def run_session(agent_cls, role: str, session_index: int, turns: int, output_dir: Path):
    session = {
        "id": f"eval-{role}-{session_index}",
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
        answer = ANSWERS[role][turn % len(ANSWERS[role])]
        session["messages"].append(message(turn_id, "user", f"第 {turn + 1} 轮补充：{answer}"))
        time.sleep(0.5)
    return {"role": role, "session": session_index, "questions": questions, "errors": errors}


def analyze(rows, roles):
    by_role = defaultdict(list)
    for row in rows:
        by_role[row["role"]].extend(q for q in row["questions"] if not is_reverse(q))

    report = {"roles": {}, "similarity": {}}
    role_tokens, unique_counts, repeat_rates, hint_rates = {}, {}, {}, {}
    for role in roles:
        questions = by_role.get(role, [])
        normalized = [normalize(q) for q in questions]
        unique = len(set(normalized))
        unique_counts[role] = unique
        repeat_rates[role] = 0.0 if not normalized else 1 - unique / len(normalized)
        tokens = set()
        for question in questions:
            tokens |= token_set(question)
        role_tokens[role] = tokens
        hints = HINTS.get(role, ())
        hint_rates[role] = (sum(any(h in q.lower() for h in hints) for q in questions) / len(questions)
                            if questions else 0.0)
        report["roles"][role] = {
            "questions": len(questions),
            "unique": unique,
            "repeat_rate": round(repeat_rates[role], 3),
            "hint_rate": round(hint_rates[role], 3),
            "samples": questions[:3],
        }

    for role_a in roles:
        report["similarity"][role_a] = {}
        for role_b in roles:
            a, b = role_tokens.get(role_a, set()), role_tokens.get(role_b, set())
            score = len(a & b) / len(a | b) if a and b else 0.0
            report["similarity"][role_a][role_b] = round(score, 3)

    averages = {}
    for role in roles:
        others = [report["similarity"][role][other] for other in roles if other != role]
        averages[role] = round(sum(others) / len(others), 3) if others else 0.0
    report["cross_role_average"] = averages
    return report


def write_markdown(report, path: Path, roles):
    lines = ["# 新增岗位差异化评测", "",
             "每个岗位按 10 轮一场跑多场；统计只取技术轮，排除最后的反问。", "",
             "| 岗位 | 问题数 | 唯一问题 | 岗位内重复率 | 分类命中率 | 与其他岗位平均相似度 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for role in roles:
        data = report["roles"].get(role, {})
        lines.append(f"| {role} | {data.get('questions', 0)} | {data.get('unique', 0)} | "
                     f"{data.get('repeat_rate', 0):.0%} | {data.get('hint_rate', 0):.0%} | "
                     f"{report['cross_role_average'].get(role, 0):.3f} |")
    lines += ["", "## 岗位间相似度（越低越差异化）", "", "| 岗位 | " + " | ".join(roles) + " |",
              "| --- | " + " | ".join("---" for _ in roles) + " |"]
    for role in roles:
        lines.append(f"| {role} | " + " | ".join(
            f"{report['similarity'][role][other]:.3f}" for other in roles) + " |")
    lines += ["", "## 每岗位题目样例", ""]
    for role in roles:
        lines.append(f"### {role}")
        for sample in report["roles"].get(role, {}).get("samples", []):
            lines.append(f"- {sample}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roles", default=",".join(ROLES))
    parser.add_argument("--sessions", type=int, default=8)
    parser.add_argument("--turns", type=int, default=10)
    parser.add_argument("--output", default="evals/results/role_diff")
    args = parser.parse_args()
    roles = [role.strip() for role in args.roles.split(",") if role.strip()]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / "raw.jsonl"

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
            row = run_session(InterviewAgent, role, index, args.turns, output)
            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            rows.append(row)
            elapsed = time.perf_counter() - started
            print(f"{role} 第 {index}/{args.sessions} 场：{len(row['questions'])}/{args.turns} 轮，"
                  f"{elapsed:.1f}s，错误 {len(row['errors'])}", flush=True)

    report = analyze(rows, roles)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, output / "report.md", roles)
    print("报告：", output / "report.md", flush=True)


if __name__ == "__main__":
    main()