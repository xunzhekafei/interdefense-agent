import type { SessionSummary } from "../types";
import { STATUS_LABELS, formatDate } from "../format";

/**
 * 练习记录独立成页。
 *
 * 之前历史挤在侧边栏里：手机上侧栏变成横排，历史卡片和删除按钮互相压住，
 * 「新建练习」还会被状态栏挡住。独立成页后，两个入口各自有完整的点击区域。
 */
export default function HistoryView({
  sessions,
  selected,
  deletingId,
  onOpen,
  onDelete,
  onNew,
}: {
  sessions: SessionSummary[];
  selected: string | null;
  deletingId: string | null;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <div className="history-page">
      <div className="history-head">
        <div>
          <span className="eyebrow">YOUR PRACTICE RECORDS</span>
          <h2>练习记录</h2>
          <p>共 {sessions.length} 场。点开任意一场可以继续查看报告。</p>
        </div>
        <button className="primary" onClick={onNew}>
          新建练习
        </button>
      </div>

      {sessions.length === 0 ? (
        <div className="history-empty">
          <p>还没有练习记录。</p>
          <button className="primary" onClick={onNew}>
            开始第一场
          </button>
        </div>
      ) : (
        <ul className="history-list">
          {sessions.map((session) => (
            <li
              key={session.id}
              className={selected === session.id ? "history-entry selected" : "history-entry"}
            >
              <button className="history-open" onClick={() => onOpen(session.id)}>
                <strong>{session.role}</strong>
                <span>
                  {session.candidate} · {formatDate(session.created_at)} ·{" "}
                  {STATUS_LABELS[session.status] ?? session.status}
                </span>
                <small>
                  {session.scene === "defense"
                    ? "毕业答辩"
                    : session.scene === "presentation"
                      ? "课程汇报"
                      : "求职面试"}
                  {session.rounds ? ` · ${session.rounds} 轮` : ""}
                </small>
              </button>
              <button
                className="history-remove"
                type="button"
                aria-label={`删除 ${session.role} 的练习记录`}
                disabled={deletingId === session.id}
                onClick={() => onDelete(session.id)}
              >
                {deletingId === session.id ? "删除中…" : "删除"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
