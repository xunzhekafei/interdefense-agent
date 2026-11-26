import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
);

// Service Worker 只在生产构建里注册：开发时它会把旧页面缓存下来，
// 改完代码刷新看不到变化，非常容易误判成「没生效」。
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch((reason) => {
      console.warn("Service Worker 注册失败，离线缓存不可用", reason);
    });
  });
}
