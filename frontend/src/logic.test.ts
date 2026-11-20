import { describe, expect, it } from "vitest";
import { draftKey, mergeDelta, nextRetryDelay } from "./logic";
import type { Message, Session } from "./types";

function session(messages: Message[]): Session {
  return {
    id: "s1",
    messages,
  } as Session;
}

const streaming = {
  id: "m1",
  turn_id: "t1",
  role: "assistant",
  text: "你",
  status: "streaming",
  input_mode: "text",
} as Message;

describe("mergeDelta", () => {
  it("appends to the streaming assistant message", () => {
    const merged = mergeDelta(session([streaming]), "好");
    expect(merged?.messages[0].text).toBe("你好");
  });

  it("ignores deltas when no snapshot has arrived yet", () => {
    expect(mergeDelta(null, "半句")).toBeNull();
  });

  it("ignores chunks when the last message is not streaming", () => {
    const done = { ...streaming, status: "completed" } as Message;
    const original = session([done]);
    expect(mergeDelta(original, "多余")).toBe(original);
  });

  it("ignores empty chunks", () => {
    const original = session([streaming]);
    expect(mergeDelta(original, "")).toBe(original);
  });
});

describe("nextRetryDelay", () => {
  it("doubles the delay", () => {
    expect(nextRetryDelay(1000)).toBe(2000);
    expect(nextRetryDelay(8000)).toBe(16000);
  });

  it("caps at 30 seconds", () => {
    expect(nextRetryDelay(30000)).toBe(30000);
    expect(nextRetryDelay(60000)).toBe(30000);
  });
});

describe("draftKey", () => {
  it("is scoped by session id", () => {
    expect(draftKey("abc")).toBe("interview.draft.abc");
  });
});