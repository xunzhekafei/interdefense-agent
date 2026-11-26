import { afterEach, describe, expect, it, vi } from "vitest";
import { api, apiUpload, deleteSession } from "./api";

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

  it("sends GET without a body and POST with one", async () => {
    // 回归：摘要卡接口只接受 POST。api() 不传 body 时发 GET，曾经因此 405，
    // 而界面上表现为一直「正在读你的讲稿」。
    const fetchMock = vi.fn(
      async (_url: string, _init?: RequestInit) =>
        new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api("/sessions");
    // fetch 的第二参一定带 signal（超时用），所以看 method 而不是整个 init
    expect(fetchMock.mock.calls[0][1]?.method).toBeUndefined();

    await api("/sessions/abc/summary-card", {});
    expect(fetchMock.mock.calls[1][1]?.method).toBe("POST");
  });

  it("uploads a script as multipart POST", async () => {
    const fetchMock = vi.fn(
      async (_url: string, _init?: RequestInit) =>
        new Response("{}", { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const file = new File(["## 研究背景"], "讲稿.md", { type: "text/markdown" });
    await apiUpload("/import-script", file);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/import-script");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBeInstanceOf(FormData);
    // 不能自己设 Content-Type：multipart 的 boundary 由浏览器生成
    expect(init?.headers).toBeUndefined();
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