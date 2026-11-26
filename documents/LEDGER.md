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
  - 摘要卡生成 / 修正 / 确认 / 下一场检验（§5，提交 `512f499`）
  - 前端三块界面：场景 + 讲稿、摘要卡确认、报告单元覆盖与检验点（§6）
  - 本机验证 + 真实模型端到端 + 四处修复（§7）
  - 答辩四维评分 spec（§8，口径 v5）
  - 讲稿文件导入 .docx / .pptx / .txt / .md（§9）
  - 试用修复：摘要卡 405 / 拖拽上传 / 报告自适应（§10–§11）
  - 报告收紧：逐题建议限长、导出补覆盖与锚定（§12）
  - 移动端第一版：PWA（§13）
  - 移动端原生骨架 + Bearer 鉴权（§14）
  - 手机端修复（按钮/布局/轮数/语音）与语音可用（§15–§16）
  - 试用工具链（§17）
  - 线上部署（双站点，§18）
- 正在做：真实用户试用准备（手机端 PWA 复验 + 招募）。
- 待验证：
  - PWA 在 Android Chrome / iOS Safari 上的安装与竖屏布局；手机端录音依赖服务端 ASR。
  - `android/` 未编译：需 Android Studio + SDK 跑一次 `:app:assembleDebug`。
- 待验证：
  - 浏览器里手动走一遍（§7/§8 的端到端都是 API 层跑的，未过 UI）。
  - 答辩报告的分散度：真实模型单场实测 3.4–5.3 分区间，尚未做「同一份讲稿多次评分」的稳定性测量。
- 已知风险：
  - 模型未配置时摘要卡是规则生成，概括质量一般（卡片 `source=rules` 会标明）。
  - 单元回链是「模型标记 + 代码兜底」两级；代码兜底宁可漏链不猜，纯语义改写的追问仍可能显示为「未覆盖」。
  - 口径升到 v5：旧面试报告的维度仍按面试四维展示，画像已混用两套维度（各自成列，不会互相吞并），但跨场次对比时要说明「答辩与面试的维度不同」。

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

## 2026-11-24 前端三块界面（待验证，未提交）

**目标**：让答辩/汇报链路能在浏览器里完整走通：选场景 → 提交讲稿 → 确认摘要卡 → 追问 → 看报告。

**改动**
- `frontend/src/types.ts`：新增 `Scene / ScriptUnit / SummaryCard / SummaryEntry / FocusItem / UnitCoverage`；`Session` 扩展 `scene/script/units/summary_card/focus`，`Report` 扩展 `unit_coverage/focus_checks`。
- `frontend/src/api.ts`：新增 `apiPatch()`（原 `api()` 固定 POST）。
- `frontend/src/components/SummaryCardView.tsx`（新增）：逐条确认/改写/驳回主张，保留/已解决/不需要待补充点；规则卡显示“模型暂不可用”提示。
- `frontend/src/App.tsx`：场景选择与讲稿输入；创建答辩场次后先拉摘要卡，确认后再进入对话；侧栏/标题/对话称呼按场景切换。
- `frontend/src/components/ReportView.tsx`：新增“陈述单元覆盖”“上一场检验点”两块，逐题显示锚定的 U 编号。
- `frontend/src/style.css`：摘要卡与报告新增样式。
- `backend/sessions.py:11`：`SUMMARY_FIELDS` 增加 `scene`，列表页能区分场景。
- `tests/test_summary_card.py`：新增 1 条，验证 `summaries()` 暴露 `scene`。

**验证**
- `npm install`：251 packages，50s。
- 后端回归 `summary_card + units + scene_skills`：44 通过。
- `npm run build`：**未完成**。沙箱内 6 分钟无输出、没有生成 `dist/`；`ls node_modules/.bin` 也超时，判断是 node_modules 目录扫描卡住，不是编译错误。需本机执行。

**决策/踩坑**
- 摘要卡确认放在“创建后、进入对话前”，而不是对话中途：理解错了，追问越准越偏；先确认再开始。
- 前端用本地状态编辑、点确认时一次 PATCH + 一次 confirm，减少请求；失败不清空编辑。
- 场景切换时自动把 `role` 填成“毕业设计答辩 / 课程汇报”，避免答辩场景还显示“岗位”下拉。
- `npm --prefix` 在 Windows 下没有生效（读到了父目录 `package.json`），改为在 `frontend/` 目录内直接 `npm install`。以后统一用目录内执行。
- 沙箱构建不可用：依赖能装（50s），但 vite/tsc 扫描 `node_modules` 时长时间无输出。构建验证放到本机，不要反复重试。

**下一步**
- 本机走一遍真实场次：提交讲稿 → 摘要卡 → 3 轮追问 → 结束 → 报告。
- 端到端确认后提交本批，commit message 引用 §6。

## 2026-11-25 本机验证与端到端修复（未提交）

**目标**：把沙箱里做不了的验证补上，并用真实模型跑一遍完整答辩闭环，确认 §6 可提交。

**验证结果（本机 Windows）**
- 后端 `python -m pytest`：**356 通过 / 2 skipped**（含新增回归）。
- 前端 `npm run build`：**成功**（199 modules，1.1s）。此前沙箱里「6 分钟无输出」不是扫描卡住，而是 `tsc` 报错——`types.ts` 里 `SessionSummary` 重复声明，`tsc --noEmit` 直接失败。
- 前端 `npx vitest run`：10 通过；`npx eslint .`：无输出（干净）。
- 真实模型端到端（DeepSeek flash，API 层，产物写临时目录）：创建答辩场次 → 摘要卡 `source=model` → 确认 → 5 轮追问 → 报告 → Markdown 导出。报告 23–43 秒，证据校验 4/4 通过。
- 摘要卡质量：模型能稳定抓到缺基线/缺口径的地方（8.1 分谁评的、40% 对比什么、92% 样本量、「现有产品没有」缺同类对比）。§5 里「真实模型质量未评估」这条风险关闭。

**改动（4 处缺陷 + 1 处提示词）**
- `script_units.py:_blocks`：标题行只用于判定段落类型，不再进单元正文。此前报告「未覆盖单元」里直接显示 `## 研究背景`，单元也把标题喂给了模型。`segment` 改为「标题优先、正文兜底」判断 section。
- `backend/service.py:confirm_summary_card`：确认后的检验点改写进 `next_focus`，不再写 `session["focus"]`。此前第一场练习的报告会声称「上一场有 5 个点没被问到」——它把本场刚确认的卡片当成了上一场遗留。
- `agent.py:_interview_report`：维度均分与加权总分改由代码从逐题分算出，并写进 summary 的 prompt 要求「直接引用」。此前结构化 `overall=2.0`，summary 正文却被模型算成 2.15，同一份报告里两个总分。
- `script_units.py:unit_of_question` + `agent.py` 回链顺序：模型漏写 `[[U3]]` 时，用问题与单元的最长公共片段补回链（≥6 字且领先次优 ≥4 字才链）。实测真实问句正确回链 9–22 字，无关泛问 ≤2 字，阈值取中间。回链顺序改为「模型标记 → 问题 → 证据」。
- `script_units.render` / `backend/agent_adapter.py`：标记规则从「确实锚定」改成「针对具体内容就标，改写措辞也要标」，并说明漏标会让报告误判未覆盖。

**回归测试（新增 4 条）**
- `test_units.py::test_segment_strips_headings_from_unit_text`
- `test_units.py::test_unit_of_question_links_paraphrased_question`（含「纯语义改写不猜」的反例）
- `test_summary_card.py`：`test_service_generates_confirms_and_inherits_focus` 增加「本场 focus 为空、next_focus 有值」断言
- `test_interview.py::test_report_final_scores_are_computed_in_code`

**决策/踩坑**
- 覆盖统计不能全押模型打标记：实测同一条问题，模型时标时不标，覆盖率在 3/5 和 4/5 之间跳。加确定性兜底后才稳定。
- 兜底阈值必须有反例测试：`unit_of_question` 明确「只共享 3 个字不链」，宁可漏也不链错——报告说某段没问到是诚实缺省，链错一段会让整个回链失去可信度。
- 真实模型的追问质量在 5 轮里有 1–2 次「答非所问」被抓住（问创新点答成耗时对比），说明追问链条有效，也说明演示时要选准备充分的讲稿。

**下一步**
- 提交 §6 + §7（含本台账）。
- 把评分维度换成答辩四维（P0）。
- 浏览器手动走一遍 UI。

## 2026-11-25 答辩四维评分（未提交，口径 v5）

**目标**：报告改用答辩自己的四个维度，去掉「面试换皮」最明显的一处证据。

**改动**
- `interview_spec.py`：`SCORING_VERSION` 4 → 5。新增 `DEFENSE_DIMENSIONS`（方法与论证严谨性 35% / 工作量与完整性 25% / 创新与个人贡献 25% / 表达与应答 15%）、`SCENE_DIMENSIONS`、`dimensions_for(scene)`、`dimension_names(scene)`、`all_dimension_names()`；新增 `RUBRICS`（每个维度评什么）与 `BANDS`（答辩自己的五档标尺）；`weighted_overall(scores, dims=None)` 支持传入场景权重，不传时行为与旧版一致。
- `agent.py`：`_interview_report()` 读 `scene`，维度 / 权重 / rubric / 分档全部从 spec 取；新增 `score_schema(dims)` 与 `report_schema(dims)`（原来的 module 级 schema 只适用于面试四维）；答辩场景下模型称呼从「面试官」改为「评委」；汇总阶段维度均分与加权总分仍由代码算，但改用该场景权重。
- `backend/profile.py`：`_dimensions()` 不再只认面试四维，改为读报告里实际存在的维度（含未知维度）；`_overall()` 按该场 `scene` 取权重。此前若直接上答辩四维，答辩场次会因为「一个维度都对不上」而 `weighted_overall` 返回 None，整场从画像里消失。
- `skills/defense-coach/SKILL.md`、`skills/course-report-coach/SKILL.md`：评分口径表换成答辩四维，并说明追问要为中心四维留下可评分材料。
- `README.md`：新增「答辩 / 汇报评分」「陈述单元锚定」两行。

**验证**
- `python -m pytest`：**362 通过 / 2 skipped**；`ruff check` 通过；`npm run build` 通过。
- 新增回归：`test_spec.py` 三场维度互异 / 权重和为 1 / 跨场景权重算分；`test_interview.py::test_defense_report_uses_defense_dimensions`（schema 键、评委称呼、加权 7.2）；`test_profile.py::test_defense_session_keeps_its_dimensions_and_weight` 与 `test_mixed_scenes_aggregate_without_losing_either`。
- 真实模型端到端（答辩讲稿 → 5 轮追问 → 报告）：维度输出 `方法与论证严谨性 3.75 / 工作量与完整性 4.25 / 创新与个人贡献 3.5 / 表达与应答 4.25`，加权 3.89，summary 与结构化数字一致。追问明显更贴近答辩（「两位评分者都是这套方法的开发者，一致性系数算过吗」「最接近的已有产品是什么，具体差在哪」）。

**决策/踩坑**
- 维度必须按场景分，不能靠技能里「在答辩语境下理解为」。换维度后报告的第一句话就变了，这是评委最容易验证的一点。
- `weighted_overall` 用面试权重去算答辩分会返回 None——这正是隐藏的坑：画像会把整场静默丢掉，不报错。所以在 `profile._dimensions()` 里先按报告实际键收集，再按场景取权重。
- 答辩四维的权重没照搬面试的 30/30/25/15：答辩现场最看重论证，给到 35%；表达只占 15%。

**下一步**
- 本机浏览器走一遍（UI 未验证）。
- 同一份讲稿重复评分 3 次，量答辩四维的稳定性（std）。
- 移动端 Android 骨架。

## 2026-11-25 讲稿文件导入（未提交）

**目标**：学生手里的讲稿是 Word 文件，只能粘贴文字不现实。

**改动**
- `backend/script_import.py`（新增）：`.txt/.md`（utf-8-sig → gb18030 兜底）、`.docx`（python-docx，含表格）、`.pptx`（python-pptx，按页取标题与正文）。Word 标题样式与幻灯片标题转成 `## 标题`，和手写讲稿走同一套段落切分。
- 防不可信输入：扩展名白名单（`.doc/.ppt` 旧格式与 PDF 明确拒绝并给替代做法）；单文件 10 MB；zip 条目数 500、解压总量 60 MB 上限；不解压到磁盘、只读不落盘；提取文本限 20000 字并与 `SessionInput.script` 上限一致，超长标记截断。
- `backend/app.py`：`POST /api/import-script`（multipart）。刻意不直接建场次——文本回到输入框让学生确认修改，符合「可检查、可修正」。
- 前端：讲稿区新增上传按钮（键盘可聚焦）+ 导入结果提示（字数、截断警告、错误原因），导入后仍可编辑。
- 依赖：`requirements-web.txt` 与 `requirements-lock.txt` 增加 `python-multipart / python-docx / python-pptx / lxml / XlsxWriter`；`tools/lock_requirements.py` 的 roots 同步增加，并把 `reportlab` 也放进 roots——之前它是手工补进锁文件的，重算时会丢。

**验证**
- `python -m pytest`：**381 通过 / 2 skipped**（新增 19 条导入测试）；`ruff` 通过；前端 `tsc + vite build + eslint + vitest` 通过。
- 真实 HTTP 上传一份 .docx（含标题样式与表格）：返回 `## 研究背景 / ## 研究方法` 和 `准确率 | 81%`，67 字。

**决策/踩坑**
- 解析放服务端：浏览器端要引解析库，且手机/电脑结果要一致；服务端解析一次，后续切分与回链全部走同一条路。
- 不直接建场次：先回填输入框。学生能发现「AI 读错了我的讲稿」，这是答辩场景里最基本的可检查。
- 先按 PPT 一并做了：`.pptx` 与 `.docx` 同为 zip+XML，python-pptx 的增量成本很小；PDF 明确不做并给出理由。
- 踩坑：`tools/lock_requirements.py` 重算会**丢掉手工补的 reportlab**，且会把整份锁降级成当前机器的旧版本。锁文件改为增量添加，roots 一并修正。
- 踩坑：测试时误以为 8000 端口空闲，`taskkill` 掉了一个监听进程——如果那是用户手动起的服务，重启 `.\start.ps1` 即可。

**下一步**
- 浏览器里试一次「上传 .docx → 摘要卡 → 追问 → 报告」。
- 可选：`.pdf`（用 pypdf，需处理扫描件与乱序）；移动端上传（手机端的文件选择器对 .docx 支持不一）。

## 2026-11-25 首次真机试用暴露的三个问题（已修）

**现象**：上传 `.md` 后页面一直「正在读你的讲稿」，服务端日志是
`GET /api/sessions/<id>/summary-card 405 Method Not Allowed`。

**根因**
- **405**：前端拉摘要卡时调用 `api(path)` 没带 body，而 `api()` 在不传 body 时发 GET；生成摘要卡是 POST。上传本身已经成功，卡在下一步。
- **看起来像卡死**：`SummaryCardView` 在 `card` 为空时无条件渲染加载动画，失败状态没有任何出口。错误只进了顶部横幅，用户看到的就是「一直转」。
- **误导性报错**：用户看到的「命令失败」不是本应用的文案，是浏览器/宿主的提示；应用里没有这句话，日志才是有效证据。

**改动**
- `frontend/src/App.tsx`：新增 `loadSummaryCard()`，统一走 POST（带 `{}` 请求体）；新增 `summaryError` 状态与 `cancelSummary()`（退回时删掉刚建的空场次）。
- `SummaryCardView`：新增 `error / onRetry / onBack` 三态——失败时显示原因、「重试」、「返回修改讲稿」，不再永久转圈。
- 讲稿区支持**拖拽上传**，并拦截浏览器的默认「打开文件」行为；`.txt/.md` 支持 **UTF-16**（记事本「Unicode」带 BOM）。
- 服务端加导入日志：`讲稿导入：<文件名>（N 字节）` / `导入成功：N 字`——下次能一眼区分「请求没到后端」和「解析失败」。
- 前端回归：`api.test.ts` 新增两条，锁住「无 body = GET、有 body = POST」和 multipart 上传（不手设 Content-Type）。

**验证**
- 后端 382 通过 / 2 skipped；前端 12 通过；`tsc`、`eslint`、`vite build` 通过。
- 用 curl 对运行中的服务实测：`.md` 上传 200，返回正确文本；`GET .../summary-card` 确实 405，与日志一致。

**经验**
- 「一直转」几乎总是缺少失败出口，而不是请求真的没结束。凡是 loading 状态，必须同时设计 error 状态。
- 排查时先看服务端日志再猜浏览器：这次 curl 一分钟就排除了整条后端链路。

## 2026-11-25 报告过长：答 1 题也出完整答辩报告（已修）

**现象**：真实试用时讲稿切出 24 段、只答 1 题就结束，报告给出四维评分（4.65）、
8 条 P0/P1/P2 建议，并列出 23 个未覆盖单元编号；用户反馈「太复杂」。

**根因**
- 没有最小证据门槛：1 道题也走完整评分 + 汇总，把一次回答的表现当成整场水平。
- 未覆盖单元逐条列编号：讲稿段数（24）多于计划轮数（15），覆盖不全本来就正常，
  逐条列出只会变成 23 条作业。
- 汇总 prompt 允许无限长：没有条数上限，模型自己发明 P0/P1/P2 分级。
- 附带两处不一致：导出标题固定「面试复盘报告」；导出把 4.65 四舍五入成 4.7，
  和 summary 里的 4.65 对不上。

**改动**
- `interview_spec.MIN_SCORED_ROUNDS = 3`；`agent._interview_report()` 在有效回答不足时
  走短报告：`overall=None`、`dimension_scores={}`、`incomplete=True`，只保留逐题反馈，
  不再调用汇总模型（省一次调用，实测报告 11 秒返回）。
- 未覆盖单元：最多列 5 个编号 + 「等 N 段」；讲稿段数多于计划轮数时，明确要求只写
  覆盖面、不许逐条列编号、不许写成逐条补准备的清单。
- 汇总 prompt：优势/短板/建议各最多 4 条、每条一句话、summary ≤200 字、不要 P0/P1/P2。
- `report_export`：标题按场景（答辩/课程汇报/面试复盘报告）；`_score` 保留两位小数去尾零，
  4.65 不再显示成 4.7；无总分时不渲染「综合评分」行。
- 前端：`Report.overall` 可为 null，报告页显示「—」+「样本不足，未评分」。

**验证**
- 后端 **385 通过 / 2 skipped**、ruff 通过；前端 12 通过、`tsc/eslint/build` 通过。
- 真实模型复跑 1 题答辩：`总分=None`、`维度={}`、11 秒、Markdown 1.7KB（此前 11.5KB）。
- 新增回归：`test_report_is_short_when_too_few_answers`、导出标题按场景、
  无总分不渲染评分行；原有评分测试补齐到 3 题以走完整路径。

**待定**
- 3 题这个门槛是拍脑袋定的，用户试用后可能需要调。
- 短报告目前不评价讲稿内容；如果用户希望「只答一题也要有内容反馈」，可改为
  只评已答题目 + 一句讲稿层面观察，但仍不给四维分。

## 2026-11-25 报告再收紧 + 导出自证（已修）

**背景**：第二轮真实试用 6 题，结构已经符合预期（四维、每节 ≤4 条、覆盖只给一句话）。
仍有两处可收：逐题建议每条 150–250 字；导出的 PDF/Markdown 看不到单元覆盖与逐题锚定。

**改动**
- 逐题评分 prompt：`suggestion` 限「一两句话、最多 80 字、不要 1/2/3 分条」。
- `report_export.to_markdown()` 新增三块，让导出的文件自身可检查：
  - `## 陈述单元覆盖`：总段数、覆盖段数与百分比、未追问编号（最多 8 个 + 「等 N 段」），
    段数多于轮数时注明「覆盖不全属正常」；
  - 逐题复盘每题加 `> 锚定讲稿：U3【结果】原文前 36 字`；
  - `## 上一场检验点`：逐条标「已检验 / 未检验」。

**验证**
- 后端 **386 通过 / 2 skipped**、ruff 通过；前端 12 通过、build 通过。
- 真实模型复跑 4 题：加权总分 3.76，四维数字与 summary 一致，覆盖提示只出现一句。
- 新增回归：导出含覆盖率/锚定/检验点；评分 prompt 必须带「最多 80 字」。

**观察（待判断）**
- 第一轮 6 题报告里 Q1–Q3 四维全是 2 分，维度间没有区分度。可能是答得确实空
  （「不是 MIT license」这一类），也可能是模型在低质量回答上直接塌到同一档。
  需要用户对着自己的回答判断是否偏严；若偏严，调分档标尺而不是加下限。

## 2026-11-25 移动端第一版：PWA（未提交）

**目标**：先让手机能用、能装、能练，再决定原生做到哪一步。范围定为练习端三屏
（创建/讲稿 → 对话 → 摘要卡确认），报告完整版留在电脑端。

**改动**
- `frontend/public/manifest.webmanifest`：standalone、portrait、主题色 `#172c2c`，192/512/maskable/apple-touch 四套图标。图标用 Pillow 现画（深底 + 对话气泡 + 三个点），不依赖设计稿。
- `frontend/public/sw.js`：安装时缓存壳；导航网络优先（部署后不会被旧页面锁住）；`/assets` 缓存优先；**`/api` 与 WebSocket 不缓存**。当前只有一个入口 bundle，所以新版本激活时清旧缓存是安全的——将来加代码分割要改。
- `frontend/index.html`：manifest、apple-touch-icon、`viewport-fit=cover`、apple 独立窗口 meta。
- `frontend/src/main.tsx`：只在生产构建注册 SW（开发时注册会缓存旧页面，容易误判「改动没生效」）。
- `components/InstallButton.tsx`：Chrome/Android 走 `beforeinstallprompt`；iOS 没有该事件，改为提示「分享 → 添加到主屏幕」；已独立窗口打开则不显示。
- 手机布局：对话区高度改为跟随视口（不再写死 620px）、`100dvh`、顶部安全区、底部 `safe-area-inset-bottom`、输入框 16px（iOS 小于 16px 会自动放大页面）。
- `backend/app.py`：新增 `/manifest.webmanifest`、`/sw.js`、`/icons/*` —— 之前只有 `/` 和 `/assets`，PWA 文件会 404。`/sw.js` 返回 `Cache-Control: no-cache`，否则浏览器一天才检查一次更新。

**验证**
- 后端 **387 通过 / 2 skipped**、ruff 通过；前端 12 通过、`tsc/eslint/build` 通过。
- 本地起服务实测：`/manifest.webmanifest` 200（manifest+json）、`/sw.js` 200（no-cache）、`/icons/icon-192.png` 200、首页含三个 PWA 标记。
- 新增回归：`test_web.py::test_pwa_assets_are_served_from_root`（前端未构建时 skip，不影响 CI）。

**决策/踩坑**
- PWA 必须先有 HTTPS 才能在手机上安装（Service Worker 只在安全上下文启用，localhost 除外）。局域网 `http://192.168.x.x:8000` 可以打开页面但**装不了、也没有离线缓存**——所以真机验证要么用隧道（cloudflared/ngrok），要么重新部署到已有证书的服务器。
- 手机录音仍是服务端 faster-whisper：笔记本演示可用，2C2G 云服务器跑不动。原生版计划改用 Android 系统语音识别。

**下一步**
- 真机安装验证（HTTPS）。
- Android 原生骨架：登录 → 创建/选讲稿 → 对话（系统 ASR）→ 摘要卡；报告只读。
- 服务端 `WEB_ALLOWED_HOSTS` 加上手机访问的域名/IP。

## 2026-11-25 赛制事实：OPPO 提供的支持（读附件 1、附件 2）

- **平台能力 SDK**（可选，自主选用）：健康服务、**互联开放能力**（设备发现与连接、
  跨设备数据传输）、超级碰一碰（NFC 一碰分享）。
- **OPPO 开放平台**：鼓励以个人开发者身份注册，把作品**上架 OPPO 软件商店**；
  官方原话是「团队工程开发能力、产品完整度的有力佐证」。上架需要 APK，PWA 不行；
  复赛阶段要填写开发者 ID、注册手机号、应用名称。
- 对项目的直接含义：
  1. 原生 APK 不只是加分项，是官方给的交付通道——移动端原生优先级成立。
  2. 「互联开放能力」与「手机练 → 电脑复盘」的跨设备故事天然契合，可作为复赛的
     差异化点（先不接，等主线稳了再评估）。
  3. 健康服务与本项目无关；超级碰一碰可做演示彩蛋，但依赖 NFC 与 OPPO 设备。
- 上架前要处理：明文 HTTP 开关 `usesCleartextTraffic`、隐私政策、录音权限说明。

## 2026-11-25 原生骨架 + Bearer 鉴权（未提交，未编译）

**目标**：给 Android 客户端一个能直接打开继续写的骨架，并把登录从「只能用 cookie」
改成原生客户端也能用。

**改动**
- `backend/app.py`：新增 `request_token()` / `websocket_token()`，优先读
  `Authorization: Bearer`，回退 cookie；HTTP API、`/api/me`、登出、WebSocket 全部接入。
  登录响应新增 `token` 字段（浏览器忽略它，行为不变）。
- `tests/test_auth.py`：新增 3 条——Bearer 免 cookie 访问、登出后 token 失效、
  WebSocket 用 Bearer 连接。
- `android/`（新增，Kotlin + Compose）：Gradle 工程、Manifest（INTERNET / RECORD_AUDIO /
  明文 HTTP）、启动图标（复用 PWA 图标生成五档 mipmap）、五屏 UI、OkHttp REST + WebSocket、
  系统语音识别、`android/README.md`（构建、真机连后端、未验证说明）。

**验证**
- 后端 **390 通过 / 2 skipped**、ruff 通过；前端未改动，此前 12 通过。
- **Android 端没有编译验证**：本机无 Android SDK。AGP 8.7.3 / Gradle 8.9 / Kotlin 2.0.21
  的构件可达（repo1 与 dl.google.com 均 200），但 wrapper jar 无法从 GitHub 下载，
  需在 Android Studio 里首次同步时生成或本机 `gradle wrapper`。

**决策/踩坑**
- 原生登录不用 cookie：OkHttp 的 CookieJar 能做，但 token 头更简单，也方便以后接
  互联 SDK 或后台任务；服务端两种都收，网页端零改动。
- 手机语音用系统识别而不是上传音频：云服务器跑不动 whisper，系统识别零成本、
  结果可改；代价是识别质量看厂商。
- 手机端报告只做结论层：小屏读长报告体验差，且无法对照讲稿原文。

**下一步**
- 装 Android Studio → 编译 → 修 API 差异 → 真机跑通一场。
- 讲稿文件上传（docx/pptx）在移动端的形态：先做「从文件选择器读文本」需要
  multipart 客户端 + 服务端已有接口。
- 评估 OPPO 互联开放能力：手机练完一题，电脑端自动出现「继续」入口。

## 2026-11-26 iPhone 真机试用：按钮变灰 + 顶部被遮（已修）

**现象**：iPhone PWA 里讲稿能上传，但「生成摘要卡」一直是灰的；顶部「新建练习」被状态栏
遮住点不到；历史卡片和删除按钮挤在一起。

**根因**
- **按钮变灰**：禁用条件里写的是 `!health?.configured`，而 `health` 只在页面加载时请求一次。
  手机上首次打开时后端/隧道可能还没就绪，请求失败后 `health` 永远是 `null` → 按钮永久禁用，
  且没有任何提示。
- **顶部被遮**：PWA 独立窗口下内容延伸到状态栏区域，侧栏只有内边距、没有安全区内边距；
  移动端还把品牌、新建、画像、历史列表挤进同一个两列网格，删除按钮用绝对定位叠在卡片上。
- **文案**：答辩场景下「面试轮数」的措辞不对。

**改动**
- `App.tsx`：health 改为失败每 5 秒重试；按钮只在 `health?.configured === false`（确定没配密钥）
  时禁用，health 未返回时允许尝试。
- 练习记录独立成页 `components/HistoryView.tsx`：整行可点、删除是独立按钮，不再绝对定位。
- 侧栏改为「品牌 + 操作组」：新建练习 / 练习记录 / 成长画像 三个按钮并列；桌面竖排、手机横排。
- 安全区：`.sidebar` 加 `env(safe-area-inset-top)`；手机端网格改单列。
- `format.ts`：状态与日期文案抽出来，历史页和会话标题共用。
- 轮数标签按场景显示「面试轮数 / 练习轮数」。

**验证**
- 前端 12 测试通过、`tsc`/`eslint`/`vite build` 通过；后端 390 通过（未改后端）。
- **手机端效果未验证**：需要 iPhone 上退出 PWA 后重新打开（Service Worker 导航走网络优先，
  但已打开的页面不会自动刷新）。

**下一步**
- 手机上确认：按钮可点、顶部不被遮、历史页可进入。
- 如果按钮仍灰，说明是另一种原因（例如 `health` 返回 configured=false），把 `/api/health`
  的返回贴出来即可定位。

## 2026-11-26 完整答辩测试反馈：语音缺失 / 轮数不生效 / 手机布局（已修）

**现象**（iPhone，完整跑一场答辩）
1. 完全没有语音；2. 选 10 轮，到 10 轮仍在继续问；3. 手机端仍是网页布局，页面乱晃、不适配。

**根因与改动**
- **语音**：本机没装 `faster-whisper`，`/api/health` 的 `speech.asr=false`，前端因此不显示麦克风。
  - 安装 `faster-whisper`（CPU，不需要 torch/nvidia 依赖）。
  - `whisper_asr.py`：未显式设 `WHISPER_MODEL` 且回落到 CPU 时，默认用 `small`（约 460MB）。
    原来默认 `large-v3-turbo` 在 CPU 上转 1 分钟音频要几十秒到几分钟，手机端体验会像卡死。
  - `start.ps1` 补上 `HF_ENDPOINT=https://hf-mirror.com`（原来只有 `start-web.ps1` 有），
    否则首次下载模型大概率超时。
- **轮数不生效**：`_unit_plan()` 只写「按单元覆盖、每个单元至少问到一次」，没有把 `rounds`
  当约束；24 段讲稿会一路问下去。
  - 改成硬上限：写明「问满 N 题必须停止提问，提示学生结束；未覆盖单元留给报告」；
    同时把「目前已经问了 X 题」注入提示词；到达上限时只做收尾、不再列未覆盖清单。
  - 新增两条回归：`test_unit_plan_enforces_round_cap`、`test_unit_plan_still_lists_units_before_cap`。
- **手机布局**：
  - 上一版把 `.conversation` 的高度改成 `auto`，消息不再内部滚动，输入框被内容顶着跑
    ——这就是「屏幕乱晃」的直接原因。
  - 改为：侧栏压成一行并 `position: sticky`；隐藏开场大标语；对话区固定
    `calc(100dvh - 190px)` 且内部滚动；输入区加底部安全区；`overflow-x: hidden`；
    正文 14px、输入框 16px。
  - 品牌文字在手机上隐藏，只留图标；三个入口按钮同行。

**验证**
- 后端 **392 通过 / 2 skipped**、ruff 通过；前端 `tsc/eslint/build` 通过。
- 手机端效果待真机确认。

**补充：PyAV 与 faster-whisper 的版本不兼容（已修）**
- 装完后实际转写报错：`TypeError: open() got an unexpected keyword argument
  'metadata_errors'`。faster-whisper 1.2.1 仍在传这个参数，PyAV 19 已移除；
  `av==18` 因网络重置没装上，所以不靠锁版本解决。
- 在 `whisper_asr._patch_av_open()` 里包一层 `av.open`，丢掉这个 kwarg。它只是
  「忽略元数据错误」的开关，语音识别用默认行为无影响；以后 av 再变也不会炸。
- 回归测试：`test_speech.py::test_av_open_patch_tolerates_metadata_errors`（没装 av 时 skip）。

**验证（真实语音）**
- 用 Windows 自带的 TTS 合成一段 4 秒英文语音 → `small` int8 转写 **1.7 秒**，
  结果与原文逐字一致；模型已缓存，冷启动加载约 3 秒。
- `/api/health` 返回 `asr: true, input_modes: ["text","voice"]`。
- 全量测试：**393 通过 / 2 skipped**。

**待验证 / 风险**
- 首次语音识别会下载 small 模型（约 460MB，走 hf-mirror），之后常驻内存。
- CPU 转写延迟：30 秒音频预计 5–15 秒（small/int8），比云端慢；2C2G 云服务器更慢，
  演示优先在本机。
- 中文识别质量还没用真人录音验证过（只有英文 TTS 样本）。
- 轮数上限依赖模型遵守提示词；报告里的 `target_rounds` 会如实记录。

## 2026-11-26 试用工具链（未提交）

**目标**：让「真实用户验证」有可解释的数字，而不是一句「大家觉得不错」。

**改动**
- `tools/trial_export.py`：只读 SQLite（`.web-data/interviews.sqlite3`）→
  `trials/sessions.csv`（每场：有效作答、计分题数、未计分、陈述单元覆盖、总分、四维）
  与 `trials/summary.md`（同人两轮前后对比、覆盖变化、每人明细）。
  默认按参与人代号匿名（P01…），`--names` 才保留真实称呼；纯确定性聚合，不调用模型。
- `tests/test_trial_export.py`：7 条（匿名化、指标、两轮配对、汇总口径、读库）。
- `documents/TRIAL.md`：招募与两轮流程、问卷 A/B（8 条封闭 + 3 条开放）、执行清单、
  隐私与「不是对照实验」的表述口径。
- `.gitignore`：忽略 `trials/`、`trials-named/`（含参与者数据）。

**验证**
- 真实库跑通：3 场 / 1 人 / 1 组两轮配对，输出「总分 3.55 → 3.86，覆盖 0.17 → 0.21」。
- 后端 **400 通过 / 2 skipped**、ruff 通过。

**下一步**
- 部署新版本到有 HTTPS 的服务器（旧部署仍是改造前代码），建 `trial` 账号。
- 第 1 轮试用；结束后用 `trial_export.py` 检查指标是否齐全。

## 2026-11-26 线上部署：双站点并存（已完成）

**目标**：把答辩复盘版上线给试用者，同时**不影响**旧 myagent 服务的评委演示账号。

**线上拓扑**

| 用途 | 域名 | 端口 | 服务 / 数据目录 |
| --- | --- | --- | --- |
| 旧版面试（评委） | `47-95-146-46.sslip.io` | 8010 | `myagent.service` / `/opt/myagent/.web-data` |
| 答辩复盘（试用） | `defense.47-95-146-46.sslip.io` | 8011 | `interdefense.service` / `/opt/interdefense-agent/.web-data` |

两个 `.web-data` 完全独立，账号不互通；nginx 按 `server_name` 分流，证书各自独立。

**配置要点**
- nginx 新站点：`client_max_body_size 20m`（讲稿上传）、WebSocket 的 `Upgrade/Connection` 头、
  `proxy_read_timeout 600s`（报告生成是分钟级）。
- 服务文件：`User=admin`、`EnvironmentFile=/etc/interdefense.env`、`--port 8011 --workers 1`。
- `/etc/interdefense.env` 从 `/etc/myagent.env` 复制后改 `WEB_ALLOWED_HOSTS`，
  权限 `root:admin 640`。语音：`WHISPER_DEVICE=cpu`、`WHISPER_MODEL=small`、`HF_ENDPOINT` 镜像。
- 证书：`certbot --nginx -d defense.47-95-146-46.sslip.io`。
- 前端产物在本机构建后上传（服务器 Node 18 不满足 Vite 7）。

**踩坑**
- 服务器 Node 18.19，Vite 7 要求 20.19+/22.12+ → 本机构建 + 传输 dist。
- `sudo npm ci` 让 `node_modules` 变成 root 所有，后续 `npm run build` 报 EACCES。
- Windows `scp -r` 传目录失败（SFTP 协商）→ 用 `tar | ssh` 管道。
- `tar -czf - frontend/dist` 会保留 `frontend/` 前缀，解压后变成 `frontend/frontend/dist`；
  正确写法是 `tar -czf - -C frontend dist`。
- 旧服务实际监听 **8010**、密钥在 `/etc/myagent.env`（不是写在 unit 里），差点按 8000 误停。
- sslip.io 支持任意子域名解析到同一 IP，所以不用买新域名。

**验证**
- `http://127.0.0.1:8011/api/health`、两个公网域名均 200。
- 旧域名用原评审账号「退出 → 重新登录」通过；新域名用 `trial` 登录通过。
- 两站点可同时访问，互不影响。

**遗留**
- 手机端在新域名上重新「添加到主屏幕」、上传 .docx、语音作答的完整复验。
- 2G 内存：两个服务 + `small` 模型常驻，观察报告生成时是否 OOM；必要时换 `base`。

## 用户/产品决定（代码里看不到的）

- 2026-11-24 选三场景：答辩 + 课程汇报 + 面试，面试保留为能力底座（不是纯答辩产品）。
- 2026-11-24 移动端走 OPPO/Android 原生，不走 PWA；降险方案是“原生只做练习端三屏，现有 Web 做电脑端复盘”。
- 2026-11-24 第一个改造包定为陈述单元锚定追问：它是其他功能的地基，也最能体现差异化。
- 2026-11-24 仓库拆分：答辩改动独立到 `interdefense-agent`，`myagent` 保持只有面试。
- 2026-11-25 讲稿必须支持文件上传（至少 Word / txt），PPT 属于后续必需项；只在输入框里粘贴文字不算可用。
- 2026-11-25 移动端路线调整为「先 PWA 保底，再 Android 原生」：PWA 用来让试用者直接扫码/点链接就能练，不必装 APK；原生负责练习端三屏，报告完整版留在电脑端。

## 维护约定

- 一个工作批次一节，标题带日期与状态（待验证 / 已上线 / 已回滚 / 已提交）。
- 写文件路径 + 行号、命令 + 结果、数字（测试数、延迟、commit hash）。
- 失败方案也记，写清为什么放弃。
- 用户/产品决定单独记（见上一节）。
- 每节结尾必须有「下一步 / 待验证」。
- 台账和代码一起提交，commit message 引用节号（如 `docs: 台账 §5`）。