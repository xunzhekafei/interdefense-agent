import { useState } from "react";

import { downloadReport } from "../api";
import type { Report } from "../types";

export default function ReportView({
  report,
  sessionId,
}: {
  report: Report;
  sessionId: string;
}) {
  const [busy, setBusy] = useState<"md" | "pdf" | null>(null);
  const [error, setError] = useState("");

  const download = async (format: "md" | "pdf") => {
    if (busy) return;
    setBusy(format);
    setError("");
    try {
      await downloadReport(sessionId, format);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "下载失败，请重试");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="report">
      <div className="report-lead">
        <div>
          <span className="eyebrow">YOUR INTERVIEW REVIEW</span>
          <h2>每一次练习，都有收获。</h2>
          <p>{report.summary}</p>
        </div>
        <div className="score">
          <strong>{report.overall}</strong>
          <span>综合评分</span>
        </div>
      </div>
      <div className="dimensions">
        {Object.entries(report.dimension_scores).map(([name, value]) => (
          <div key={name}>
            <span>{name}</span>
            <strong>
              {value.toFixed(1)} <small>/ 10</small>
            </strong>
            <meter min="0" max="10" value={value} />
          </div>
        ))}
      </div>
      <div className="review-grid">
        {[
          ["你的优势", report.strengths],
          ["值得加强", report.weaknesses],
          ["下一步练习", report.recommendations],
        ].map(([title, items]) => (
          <section key={title as string}>
            <h3>{title}</h3>
            <ul>
              {(items as string[]).map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      <h3>逐题复盘</h3>
      {report.per_question?.map((item, i) => (
        <details key={i}>
          <summary>
            <span>{String(i + 1).padStart(2, "0")}</span>
            {item.question}
          </summary>
          <div className="question-scores">
            {Object.keys(report.dimension_scores).map((name) => (
              <span key={name}>
                {name}：{String(item[name] ?? "—")}
              </span>
            ))}
          </div>
          <blockquote>{item.evidence}</blockquote>
          {item.evidence_verified === false && (
            <small className="evidence-warning">
              这条证据未通过原话校验，可能是模型改写或概括的，仅供参考
            </small>
          )}
          <p>{item.suggestion}</p>
        </details>
      ))}
      {report.skipped_questions?.length ? (
        <>
          <h3>未计分的轮次</h3>
          <p className="report-note">
            这些轮次没有有效作答（误触、问候、跳过或反问），已从均分中剔除，
            不影响综合评分。
          </p>
          {report.skipped_questions.map((item, i) => (
            <details key={i} className="skipped-question">
              <summary>
                <span>{String(i + 1).padStart(2, "0")}</span>
                {item.question}
              </summary>
              <blockquote>{item.answer || "（空）"}</blockquote>
              <small className="evidence-warning">
                {item.reason_text || item.reason}
              </small>
            </details>
          ))}
        </>
      ) : null}
      <div className="report-downloads">
        <button
          className="secondary"
          disabled={busy !== null}
          onClick={() => void download("md")}
        >
          {busy === "md" ? "生成中…" : "下载 Markdown ↓"}
        </button>
        <button
          className="secondary"
          disabled={busy !== null}
          onClick={() => void download("pdf")}
        >
          {busy === "pdf" ? "生成中…" : "下载 PDF ↓"}
        </button>
        <button
          className="secondary"
          onClick={() => {
            const url = URL.createObjectURL(
              new Blob([JSON.stringify(report, null, 2)], {
                type: "application/json",
              }),
            );
            const a = document.createElement("a");
            a.href = url;
            a.download = "interview-report.json";
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          下载 JSON ↓
        </button>
      </div>
      {error ? <small className="evidence-warning">{error}</small> : null}
    </div>
  );
}