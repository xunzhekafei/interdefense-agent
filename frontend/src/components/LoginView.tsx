import { useState } from "react";
import { login } from "../api";

export default function LoginView({
  onSuccess,
}: {
  onSuccess: (user: string) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const state = await login(username.trim(), password);
      onSuccess(state.user ?? "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <span className="login-mark">i.</span>
        <h1>面试练习室</h1>
        <p>请输入评审账号</p>
        <label>
          用户名
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>
        <label>
          密码
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}
        <button className="primary" disabled={busy || !username.trim() || !password}>
          {busy ? "正在登录…" : "登录"}
        </button>
      </form>
    </div>
  );
}
