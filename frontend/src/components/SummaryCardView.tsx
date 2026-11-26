import { useEffect, useState } from "react";

import type { SummaryCard, SummaryEntry } from "../types";

/** 一条主张：确认 / 改写 / 驳回。改写后就以学生的话为准。 */
function ClaimRow({
  entry,
  onChange,
}: {
  entry: SummaryEntry;
  onChange: (patch: Partial<SummaryEntry>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(entry.edited_text || entry.text);

  useEffect(() => {
    setDraft(entry.edited_text || entry.text);
  }, [entry.edited_text, entry.text]);

  return (
    <article className={`summary-item ${entry.status}`}>
      <div className="summary-item-head">
        <span className="unit-badge">{entry.unit_ref}</span>
        <small>
          {entry.status === "confirmed"
            ? "已确认"
            : entry.status === "rejected"
              ? "已标记为不准确"
              : "待确认"}
        </small>
      </div>
      {editing ? (
        <textarea
          value={draft}
          rows={2}
          maxLength={200}
          onChange={(event) => setDraft(event.target.value)}
        />
      ) : (
        <p>{entry.edited_text || entry.text}</p>
      )}
      <div className="summary-actions">
        {editing ? (
          <>
            <button
              type="button"
              className="summary-action primary-lite"
              onClick={() => {
                const text = draft.trim();
                onChange({
                  status: "confirmed",
                  edited_text: text && text !== entry.text ? text : null,
                });
                setEditing(false);
              }}
            >
              保存改写
            </button>
            <button
              type="button"
              className="summary-action"
              onClick={() => {
                setEditing(false);
                setDraft(entry.edited_text || entry.text);
              }}
            >
              取消
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className={`summary-action ${entry.status === "confirmed" ? "active" : ""}`}
              onClick={() => onChange({ status: "confirmed" })}
            >
              是我说的
            </button>
            <button
              type="button"
              className="summary-action"
              onClick={() => setEditing(true)}
            >
              改写
            </button>
            <button
              type="button"
              className={`summary-action ${entry.status === "rejected" ? "active" : ""}`}
              onClick={() => onChange({ status: "rejected" })}
            >
              不是我说的
            </button>
          </>
        )}
      </div>
    </article>
  );
}

/** 一条待补充点：保留 / 已解决 / 不需要。 */
function QuestionRow({
  entry,
  onChange,
}: {
  entry: SummaryEntry;
  onChange: (patch: Partial<SummaryEntry>) => void;
}) {
  return (
    <article className={`summary-item ${entry.status}`}>
      <div className="summary-item-head">
        <span className="unit-badge">{entry.unit_ref}</span>
        <small>
          {entry.status === "resolved"
            ? "已解决"
            : entry.status === "dismissed"
              ? "不需要追问"
              : "下一场会重点问"}
        </small>
      </div>
      <p>{entry.text}</p>
      <div className="summary-actions">
        <button
          type="button"
          className={`summary-action ${entry.status === "pending" ? "active" : ""}`}
          onClick={() => onChange({ status: "pending" })}
        >
          保留
        </button>
        <button
          type="button"
          className={`summary-action ${entry.status === "resolved" ? "active" : ""}`}
          onClick={() => onChange({ status: "resolved" })}
        >
          已解决
        </button>
        <button
          type="button"
          className={`summary-action ${entry.status === "dismissed" ? "active" : ""}`}
          onClick={() => onChange({ status: "dismissed" })}
        >
          不需要
        </button>
      </div>
    </article>
  );
}

export default function SummaryCardView({
  card,
  busy,
  error,
  onRetry,
  onBack,
  onConfirm,
}: {
  card: SummaryCard | null;
  busy: boolean;
  error?: string | null;
  onRetry?: () => void;
  onBack?: () => void;
  onConfirm: (claims: SummaryEntry[], questions: SummaryEntry[]) => Promise<void>;
}) {
  const [claims, setClaims] = useState<SummaryEntry[]>(card?.claims ?? []);
  const [questions, setQuestions] = useState<SummaryEntry[]>(
    card?.open_questions ?? [],
  );

  // 重新生成卡片时同步本地编辑，避免还显示上一版
  useEffect(() => {
    setClaims(card?.claims ?? []);
    setQuestions(card?.open_questions ?? []);
  }, [card]);

  if (!card) {
    // 失败必须能看出来并且能重试：一直转圈会让人以为程序卡死，
    // 而实际原因（405、网络、模型超时）就藏在一次不会结束的请求后面。
    if (error) {
      return (
        <div className="summary-page">
          <div className="summary-error" role="alert">
            <strong>没能生成摘要卡</strong>
            <p>{error}</p>
            <div className="summary-actions">
              <button type="button" className="primary" onClick={onRetry} disabled={busy}>
                {busy ? "正在重试…" : "重试"}
              </button>
              {onBack && (
                <button type="button" onClick={onBack}>
                  返回修改讲稿
                </button>
              )}
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="summary-page">
        <div className="summary-loading">
          <span className="spinner" />
          <div>
            <strong>正在读你的讲稿</strong>
            <p>整理核心主张、找出容易被追问的地方，请稍候…</p>
          </div>
        </div>
      </div>
    );
  }

  const update = (
    list: SummaryEntry[],
    setList: (items: SummaryEntry[]) => void,
    id: string,
    patch: Partial<SummaryEntry>,
  ) => setList(list.map((item) => (item.id === id ? { ...item, ...patch } : item)));

  return (
    <div className="summary-page">
      <div className="summary-head">
        <span className="eyebrow">CHECK THE AI&apos;S UNDERSTANDING</span>
        <h1>先确认理解，再开始追问</h1>
        <p>
          下面是我从讲稿里读到的核心主张，以及准备重点追问的地方。
          确认或改写后，下一场会优先检验这些点。
        </p>
        {card.source === "rules" && (
          <small className="summary-source">
            模型暂不可用，这张卡由规则生成，措辞可能比较生硬，建议逐条改写。
          </small>
        )}
      </div>

      <section className="summary-section">
        <div className="summary-section-head">
          <h3>我理解的核心主张</h3>
          <small>
            {claims.filter((item) => item.status === "confirmed").length} /{" "}
            {claims.length} 已确认
          </small>
        </div>
        {claims.map((entry) => (
          <ClaimRow
            key={entry.id}
            entry={entry}
            onChange={(patch) => update(claims, setClaims, entry.id, patch)}
          />
        ))}
      </section>

      <section className="summary-section">
        <div className="summary-section-head">
          <h3>我准备重点追问的地方</h3>
          <small>保留的点会进入下一场检验</small>
        </div>
        {questions.length === 0 ? (
          <p className="summary-empty">这段讲稿里没有发现明显的证据缺口。</p>
        ) : (
          questions.map((entry) => (
            <QuestionRow
              key={entry.id}
              entry={entry}
              onChange={(patch) => update(questions, setQuestions, entry.id, patch)}
            />
          ))
        )}
      </section>

      <div className="summary-footer">
        <button
          className="primary"
          disabled={busy}
          onClick={() => void onConfirm(claims, questions)}
        >
          {busy ? "正在保存…" : "确认理解，开始练习 ↗"}
        </button>
        <small>
          确认后仍可回到这场记录里修改；没处理的主张会按「已确认」保存。
        </small>
      </div>
    </div>
  );
}