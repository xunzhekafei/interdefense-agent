import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("api", () => {
  it("turns a hung request into a timeout error", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () =>
              reject(new DOMException("Aborted", "AbortError")),
            );
          }),
      ),
    );

    const promise = api("/sessions");
    const assertion = expect(promise).rejects.toThrow("请求超时，请稍后重试");
    await vi.advanceTimersByTimeAsync(15_000);
    await assertion;
  });

  it("prefers the server's Chinese detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "当前场次仍在处理" }), {
            status: 409,
          }),
      ),
    );
    await expect(api("/sessions")).rejects.toThrow("当前场次仍在处理");
  });
});