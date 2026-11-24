# interdefense-agent 开发台账

> 开始：2026-11-24
> 用途：每个工作批次追加一节；既是进度记录，也是交接材料。
> 续接：读「当前状态」+ 最后两节 + `git log --oneline -8`。
> 行号说明：§2、§3 以提交 `92069f6` 为准；§5 尚未提交，行号以当前工作区为准。

## 当前状态（随时更新）

- 目标：把上游 `myagent` 的 AI 面试运行时改造成「答辩 / 课程汇报复盘」学习工具，参加第二十届全国大学生软件创新大赛赛题 1（面向移动终端），同时保留面试场景。
- 已完成：
  - 赛题解析与仓库基线（§1）
  - 陈述单元锚定追问（§2，提交 `92069f6`）
  - 三场景技能（§3，提交 `92069f6`）
  - 仓库拆分并推送（§4，远程 `main` 已同步）
  - 摘要卡生成 / 修正 / 确认 / 下一场检验（§5，未提交）
- 正在做：摘要卡闭环收尾，准备前端接入。
- 待验证：
  - 前端「选场景 / 粘贴讲稿 / 摘要卡确认」三块尚未实现，端到端链路目前只到 API。
  - 真实模型（非规则兜底）生成的摘要卡质量未评估。
  - `test_web.py`、`test_speech.py` 在沙箱内无法稳定运行（见 §2 验证），需本机复核。
- 已知风险：
  - 评分维度仍是面试四维（用答辩语境解释），真正的答辩四维未接入；改它要同时动 `interview_spec.py`、`agent.py` 的 schema、`SCORING_VERSION`、`profile.py` 历史聚合。
  - 模型未配置时摘要卡是规则生成，概括质量一般（卡片 `source=rules` 会标明）。
  - §5 改动尚未提交；工作区有推送过程留下的未跟踪文件 `push.log`（建议删除或加入 `.gitignore`，不要提交）。

## 2026-11-24 赛题解析与仓库基线（已完成）

**目标**：确认比赛硬约束，判断上游项目可复用程度。

**改动**
- 无代码改动；解析 `附件1`（赛题详情）、`附件2`（可支持能力清单）、`附件8`（评分标准）三份 PDF。
- 上游仓库克隆至 `myagent/`，HEAD `7c539ad`。

**验证**
- 阅读 `README.md`、`documents/PROGRESS.md`、`documents/AGENT_RUNTIME.md`，确认已有能力：逐题流式、证据逐字校验、跨场次弱点生命周期、场次隔离与断线恢复。

**决策/踩坑**
- 评分权重以 PDF 为准：初赛创新 40 / 应用 20 / 技术 25 / 工程 15；复赛创新 20 / 应用 30 / 技术 30 / 工程 20。md 摘要漏了“工程从 15 升到 20、架构从 5 升到 10”。
- 上游 `validate_evidence`（证据必须是回答的逐字子串）直接支撑“答辩证据回链”，因此不做重写，只在单元层复用。

**下一步**
- 定场景边界与移动端路线（见「用户/产品决定」）。

## 2026-11-24 陈述单元锚定追问（已提交 92069f6）

**目标**：让追问锚定讲稿的具体段落，而不是像面试一样只追上一句话。

**改动**
- `script_units.py:179` `segment()`：按标题 / 空行 / 句号切单元，保留 `start/end` 偏移；超长时合并相邻单元而不是丢弃（上限 24 个、单元 600 字）。
- `script_units.py:224` `split_markers()`：解析并剥离 `[[U2]]`；`:255` `unit_of_quote()` 证据回链；`:266` `coverage()` 覆盖统计。
- `backend/service.py:145` `create(..., scene, script)`：讲稿归一化、切单元、入库。
- `backend/service.py` 回合收尾：剥离标记并写入 `message["unit_ref"]`。
- `backend/app.py:81` `SessionInput` 增加 `scene` / `script`。
- `backend/agent_adapter.py:182` `reply()`：答辩/汇报注入单元清单与锚定规则。
- `agent.py:2730` `_interview_report()`：评分时对照锚定单元；`:2920` 报告输出 `unit_coverage`。
- `tests/test_units.py`：19 条。

**验证**
- `python -m pytest tests/test_units.py -q`：19 通过。
- 纯逻辑回归 `test_spec + test_evidence + test_units`：41 通过（当时）。
- `ruff check`：通过。

**决策/踩坑**
- 标记用行内 `[[U2]]` 而不是结构化 JSON：保持现有 WebSocket 流式协议，收尾时统一剥离，展示层看不到标记。
- 单元必须保留原文偏移：报告里的证据要能回到用户提交的原文，这是“可检查”的底座。
- 踩坑：替换 `plan_block` 时漏了首行缩进，并把 `unit_block` 整段覆盖，直接 `IndentationError`。修法是按“前一行 + 目标行”整体替换，替换后立刻跑单测。

**下一步**
- 三场景技能。

## 2026-11-24 三场景技能（已提交 92069f6）

**目标**：答辩、课程汇报、面试各有一套行为规则，避免“面试换皮”。

**改动**
- `skills/defense-coach/SKILL.md`：评委视角、证据优先、单个单元最多 2 层追问、不设反问、编号不念出来。
- `skills/course-report-coach/SKILL.md`：助教视角、重点追问分工与个人贡献、允许一次提示、轮次更短。
- `backend/agent_adapter.py:21` `SCENE_SKILLS` 场景路由；`:108` `_unit_plan()` 用“单元覆盖”替换面试轮数配额；技能缺失回退 `mock-interviewer`。
- `tests/test_scene_skills.py`：9 条。

**验证**
- `python -m pytest tests/test_scene_skills.py -q`：9 通过。
- 面试场景两条回归（`test_reply_injects_round_plan`、`test_reply_forces_reverse_on_last_round`）：2 通过。

**决策/踩坑**
- 技能分两份而不是一个技能加 `if`：三场景的追问对象不同，长上下文里容易串到面试节奏。
- 答辩/汇报不再注入“项目深挖 / 反问”配额，改为“尚未覆盖的单元列表”。
- 技能里的评分口径写成“现有四维在答辩语境下的解释”，没有宣称已换四维——技能与代码保持一致，避免“技能说要评 X、报告里没有 X”。

**下一步**
- 摘要卡闭环。

## 2026-11-24 仓库拆分与推送（已推送）

**目标**：`myagent` 保持纯面试版，答辩改造独立成仓库。

**改动**
- 以 `myagent` 的 HEAD 本地克隆 `interdefense-agent`，复制 10 个改动文件；移除本地 origin 后提交 `92069f6`。
- `myagent` 执行 `reset --hard` 并删除 5 个新增项，恢复到 `7c539ad`、工作区干净。
- README / 页面标题 / FastAPI title 改为 InterDefense Studio。

**验证**
- 新仓库 53 条纯逻辑测试通过后才恢复 `myagent`。
- `myagent` 中 `grep script_units|unit_ref|defense-coach` 无结果；`git ls-files -m` 为空。
- 远程 `main` 已由用户在网页端建库后推送成功。

**决策/踩坑**
- 保留上游 git 历史（MIT 来源可追溯），只移除 origin。
- 踩坑：本地仓库是 `--depth 1` 浅克隆，push 一直被拒；用户在本机处理后才成功。**以后 fork 前先确认是否浅克隆。**
- 沙箱访问 `127.0.0.1:7897` 代理被拦、直连 GitHub 被 reset，推送只能在本机执行。

**下一步**
- 摘要卡闭环。

## 2026-11-24 摘要卡闭环（待验证，未提交）

**目标**：让用户确认/修正 AI 对讲稿的理解，并把确认结果变成下一场的定向检验点。

**改动**
- `script_summary.py:140` `build_card()`：模型结果优先，伪造 `unit_id` 丢弃，为空则规则兜底；`source` 标注 `model|rules`。
- `script_summary.py:174` `apply_edits()` 逐条修正；`:182` `confirm()`；`:192` `focus_items()` 生成检验点（带单元原句 `quote`）；`:222` `focus_checks()` 报告核对。
- `backend/service.py:385` `summary_card()`（生成走 `memory_executor`，不占对话队列）；`:414` `patch_summary_card()`；`:427` `confirm_summary_card()`。
- `backend/service.py:145` `create()` 增加 `focus_from`：服务端读上一场卡片，不接受客户端伪造的检验点。
- `backend/app.py:307/319/333` 三个路由；`SessionInput` 增加 `focus_from`。
- `backend/agent_adapter.py:291` `summarize()`；`reply()` 注入上一场检验点；`report()` 传 `focus`。
- `agent.py:2926` 汇总阶段统计 `focus_checks`，未检验的点在 summary 里如实提醒。
- `tests/test_summary_card.py`：15 条。

**验证**
- `python -m pytest tests/test_summary_card.py -q`：15 通过。
- 合并回归 `summary_card + units + scene_skills + spec`：53 通过（15 + 19 + 9 + 10）。
- `ruff check`：All checks passed。

**决策/踩坑**
- 规则兜底必须保留：模型不可用时仍能出卡；`source` 明确告诉用户这张卡是不是模型写的。
- 检验点用单元原句前 80 字而不是 U 编号：下一场讲稿会重新切分，编号会变。
- 报告核对用 `quote` 前 16 字匹配：追问会改写措辞，精确匹配必漏；这是启发式，只说明“是否问及”，不宣称“是否答好”。
- 确认语义：`pending` 主张一键转 `confirmed`，`rejected` 不进下一场；`open_questions` 未确认也进入检验（缺证据本身就该被问），只有 `dismissed` 才排除。
- 踩坑：规则 claim 取到了 Markdown 标题（`## 研究背景`），修 `_first_sentence` 先剥标题再取正文；测试断言 `is` 改 `==`（SQLite 反序列化出来是新对象）。

**下一步**
- 提交本批改动（含本台账）。
- 前端三块界面：场景 + 讲稿、摘要卡确认、报告里的单元覆盖与检验结果。

## 用户/产品决定（代码里看不到的）

- 2026-11-24 选三场景：答辩 + 课程汇报 + 面试，面试保留为能力底座（不是纯答辩产品）。
- 2026-11-24 移动端走 OPPO/Android 原生，不走 PWA；降险方案是“原生只做练习端三屏，现有 Web 做电脑端复盘”。
- 2026-11-24 第一个改造包定为陈述单元锚定追问：它是其他功能的地基，也最能体现差异化。
- 2026-11-24 仓库拆分：答辩改动独立到 `interdefense-agent`，`myagent` 保持只有面试。

## 维护约定

- 一个工作批次一节，标题带日期与状态（待验证 / 已上线 / 已回滚 / 已提交）。
- 写文件路径 + 行号、命令 + 结果、数字（测试数、延迟、commit hash）。
- 失败方案也记，写清为什么放弃。
- 用户/产品决定单独记（见上一节）。
- 每节结尾必须有「下一步 / 待验证」。
- 台账和代码一起提交，commit message 引用节号（如 `docs: 台账 §5`）。