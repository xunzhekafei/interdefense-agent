import { afterEach, describe, expect, it, vi } from "vitest";
import { api, deleteSession } from "./api";

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

  it("deletes a session with the DELETE method", async () => {
    const fetchMock = vi.fn(
      async (_url: string, _init?: RequestInit) =>
        new Response(null, { status: 204 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await deleteSession("abc123");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sessions/abc123");
    expect(init?.method).toBe("DELETE");
  });
});