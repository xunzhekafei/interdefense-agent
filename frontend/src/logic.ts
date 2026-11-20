import type { Session } from "./types";

/** 合并一条流式增量；快照还没到或最后一条不是流式回复时原样返回。 */
export function mergeDelta(
  session: Session | null,
  chunk: string,
): Session | null {
  if (!session || !chunk) return session;
  const messages = session.messages;
  const last = messages[messages.length - 1];
  if (!last || last.role !== "assistant" || last.status !== "streaming")
    return session;
  return {
    ...session,
    messages: [...messages.slice(0, -1), { ...last, text: last.text + chunk }],
  };
}

/** 断线重连退避：1s → 2s → 4s… 上限 30s。 */
export function nextRetryDelay(current: number): number {
  return Math.min(30_000, current * 2);
}

/** 草稿按场次隔离，避免不同面试互相覆盖。 */
export function draftKey(sessionId: string): string {
  return `interview.draft.${sessionId}`;
}