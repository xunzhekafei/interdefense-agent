const DEFAULT_TIMEOUT = 15_000;
// 本地 Whisper 首次使用要下载模型，之后一次推理也要十几秒；给足时间但不无限挂起。
const TRANSCRIBE_TIMEOUT = 600_000;

/** fetch + 超时 + 外部取消。超时与用户主动取消要给出不同文案。 */
async function request(
  input: string,
  init: RequestInit = {},
  timeout = DEFAULT_TIMEOUT,
): Promise<Response> {
  const controller = new AbortController();
  const external = init.signal;
  const forward = () => controller.abort();
  if (external?.aborted) controller.abort();
  external?.addEventListener("abort", forward, { once: true });
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (reason) {
    if (controller.signal.aborted) {
      throw new Error(
        external?.aborted ? "请求已取消" : "请求超时，请稍后重试",
        { cause: reason },
      );
    }
    throw reason;
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", forward);
  }
}

async function readError(response: Response, fallback: string): Promise<string> {
  const error = await response.json().catch(() => ({}));
  return typeof error.detail === "string" ? error.detail : fallback;
}

export async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await request(
    `/api${path}`,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) {
    throw new Error(await readError(response, "请求失败，请检查输入或服务状态"));
  }
  return response.json();
}

/** 上传一段录音，拿回转写文字。**不写入会话**——文字填进输入框，由用户确认后再走 answer 提交。
 *
 * 不能复用上面的 `api()`：它固定发 JSON 并把 body 序列化。
 */
export async function transcribe(
  sessionId: string,
  audio: Blob,
  mimeType: string,
  signal?: AbortSignal,
): Promise<string> {
  const response = await request(
    `/api/sessions/${sessionId}/transcribe`,
    {
      method: "POST",
      headers: { "Content-Type": mimeType || "application/octet-stream" },
      body: audio,
      signal,
    },
    TRANSCRIBE_TIMEOUT,
  );
  if (!response.ok) {
    throw new Error(await readError(response, "语音识别失败，请重试"));
  }
  return (await response.json()).text as string;
}

export type AuthState = { user: string | null; enabled: boolean };

/** 当前登录状态。401 表示「启用了鉴权但没登录」。 */
export async function me(): Promise<AuthState> {
  const response = await request("/api/me", {}, 10_000);
  if (response.status === 401) return { user: null, enabled: true };
  if (!response.ok) throw new Error("无法检查登录状态");
  return response.json();
}

export async function login(username: string, password: string): Promise<AuthState> {
  const response = await request("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    throw new Error(await readError(response, "用户名或密码错误"));
  }
  return response.json();
}

export async function logout(): Promise<void> {
  await request("/api/logout", { method: "POST" }, 10_000).catch(() => {});
}

/** 删除一场面试（快照 + 全部事件）。 */
export async function deleteSession(sessionId: string): Promise<void> {
  const response = await request(
    `/api/sessions/${sessionId}`,
    { method: "DELETE" },
    10_000,
  );
  if (!response.ok) {
    throw new Error(await readError(response, "删除失败，请重试"));
  }
}

export function connectSession(id: string) {
  return new WebSocket(
    `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/sessions/${id}/ws`,
  );
}