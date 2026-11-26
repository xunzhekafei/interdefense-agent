export type InputMode = "text" | "voice";

export type Message = {
  id: string;
  turn_id: string;
  role: "user" | "assistant";
  text: string;
  status: "streaming" | "completed" | "interrupted";
  input_mode: InputMode;
};
export type Report = {
  /** 有效回答不足 3 题时为 null：不给分，只保留逐题反馈 */
  overall: number | null;
  /** 本次练习未完成（回答太少），报告只含逐题反馈 */
  incomplete?: boolean;
  summary: string;
  dimension_scores: Record<string, number>;
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
  per_question?: ({
    question: string;
    evidence: string;
    suggestion: string;
    /** 证据是否通过了「必须是候选人逐字原话」的机器校验 */
    evidence_verified?: boolean;
    /** 这一问锚定到的陈述单元编号 */
    unit_ref?: string[];
  } & Record<string, unknown>)[];
  /** 误触/问候/跳过/反问等没有有效作答的轮次，已从均分中剔除 */
  skipped_questions?: {
    question: string;
    answer: string;
    reason: string;
    reason_text?: string;
  }[];
  /** 本场目标总题数 */
  target_rounds?: number;
  /** 答辩/汇报：每个陈述单元被追问了几次 */
  unit_coverage?: UnitCoverage;
  /** 答辩/汇报：上一场确认的检验点这一场是否被问到 */
  focus_checks?: FocusItem[];
};
export type Pressure = "温和" | "标准" | "压力";
export type SessionMode = "text" | "voice";
export type Scene = "interview" | "defense" | "presentation";

export type ScriptUnit = {
  id: string;
  section?: string;
  text: string;
  start?: number;
  end?: number;
};

export type SummaryStatus =
  | "pending"
  | "confirmed"
  | "rejected"
  | "resolved"
  | "dismissed";

export type SummaryEntry = {
  id: string;
  unit_ref: string;
  text: string;
  status: SummaryStatus;
  edited_text?: string | null;
};

/** AI 对讲稿的理解：学生确认/修正后才进入追问。 */
export type SummaryCard = {
  version: number;
  /** model = 模型概括；rules = 模型不可用时的规则兜底 */
  source: "model" | "rules";
  claims: SummaryEntry[];
  open_questions: SummaryEntry[];
  confirmed: boolean;
  confirmed_at: string | null;
};

/** 上一场确认、这一场应定向检验的点。 */
export type FocusItem = {
  kind: "claim" | "question";
  id: string;
  text: string;
  /** 该点所在单元的原文开头，用于跨场次找回同一段 */
  quote: string;
  unit_ref: string;
  checked?: boolean;
};

export type UnitCoverage = {
  total: number;
  covered: number;
  ratio: number | null;
  units: {
    id: string;
    section?: string;
    text: string;
    references: number;
    covered: boolean;
  }[];
  uncovered: { id: string; section?: string; text: string }[];
};

export type SessionSummary = {
  id: string;
  candidate: string;
  role: string;
  created_at: string;
  status: string;
  /** 老场次没有这个字段，按文字处理 */
  mode?: SessionMode;
  /** 目标总题数（含开场和反问）；老场次按 15 处理 */
  rounds?: number;
  /** 老场次没有场景字段，按求职面试处理 */
  scene?: Scene;
};
export type Session = SessionSummary & {
  background: string;
  pressure?: Pressure;
  scene?: Scene;
  script?: string;
  units?: ScriptUnit[];
  summary_card?: SummaryCard | null;
  /** 上一场确认的检验点，本场会定向追问 */
  focus?: FocusItem[];
  focus_from?: string | null;
  messages: Message[];
  report: Report | null;
  active_turn: string | null;
  error: string | null;
  seq: number;
  requests: string[];
};
export type Action = "start" | "answer" | "finish" | "cancel" | "retry";

/** 报告生成过程中逐题推来的结果；四个维度名也是这个对象的键。 */
export type ScoredQuestion = {
  question: string;
  evidence: string;
  suggestion: string;
  [key: string]: string | number;
};

export type DimensionTrend = {
  average: number;
  first: number;
  latest: number;
  delta: number;
  best: number;
  worst: number;
  samples: number;
};

export type WeakPoint = {
  text: string;
  theme: string | null;
  role: string;
  first_seen: string;
  last_seen: string;
  times_seen: number;
  improved: boolean;
  archived: boolean;
  interval_days: number;
  review_streak: number;
  next_review: string | null;
  due: boolean;
};

export type Profile = {
  sessions: number;
  range?: { from: string; to: string };
  overall?: {
    average: number;
    first: number;
    latest: number;
    delta: number;
    best: number;
    worst: number;
  };
  timeline: {
    id: string;
    created_at: string;
    role: string;
    pressure: Pressure;
    overall: number;
    dimensions: Record<string, number>;
    scoring_version?: number;
  }[];
  /** 出现多个版本说明评分口径变过，跨版本的分数不完全可比 */
  scoring_versions?: number[];
  dimensions: Record<string, DimensionTrend>;
  roles: {
    role: string;
    sessions: number;
    average: number;
    latest: number;
    dimensions: Record<string, number>;
  }[];
  weakest: ({ name: string } & DimensionTrend)[];
  recurring: { text: string; count: number }[];
  recent_weaknesses: { text: string; role: string; created_at: string }[];
  /** 跨场次聚合出的弱点，带生命周期与复习日期 */
  weak_points: WeakPoint[];
  /** 已到复习日的弱点 */
  due_reviews: WeakPoint[];
};

export type SpeechCapabilities = {
  asr: boolean; // 这台机器有没有语音识别能力（依赖装没装）
  ready: boolean; // 模型是否已加载（有能力 ≠ 已就绪）
  tts: boolean;
  input_modes: string[];
};

export type Health = {
  configured: boolean;
  speech: SpeechCapabilities;
};
