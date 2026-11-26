import { useEffect, useState } from "react";

/** beforeinstallprompt 的事件类型；TS 的 DOM 库还没有它。 */
type InstallPrompt = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

function runningStandalone(): boolean {
  if (window.matchMedia("(display-mode: standalone)").matches) return true;
  // iOS Safari 用私有字段表示「已从主屏幕打开」
  return (navigator as Navigator & { standalone?: boolean }).standalone === true;
}

function isIos(): boolean {
  const ua = navigator.userAgent;
  return /iPad|iPhone|iPod/.test(ua) ||
    // iPadOS 13+ 伪装成 Mac，用触摸点数区分
    (ua.includes("Macintosh") && navigator.maxTouchPoints > 1);
}

/**
 * 「安装到桌面」入口。
 *
 * Chrome/Edge/Android 走 beforeinstallprompt；iOS Safari 没有这个事件，
 * 只能提示用户用「分享 → 添加到主屏幕」。已经在独立窗口打开时不显示。
 */
export default function InstallButton() {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  const [installed, setInstalled] = useState(runningStandalone);
  const [hint, setHint] = useState(false);

  useEffect(() => {
    const onPrompt = (event: Event) => {
      event.preventDefault();          // 自己决定什么时候弹出，别打断首次使用
      setPrompt(event as InstallPrompt);
    };
    const onInstalled = () => {
      setPrompt(null);
      setInstalled(true);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (installed) return null;

  if (prompt) {
    return (
      <button
        type="button"
        className="install-button"
        onClick={async () => {
          await prompt.prompt();
          await prompt.userChoice;
          setPrompt(null);
        }}
      >
        安装到桌面
      </button>
    );
  }

  if (!isIos()) return null;

  return (
    <span className="install-wrap">
      <button type="button" className="install-button" onClick={() => setHint(!hint)}>
        安装到桌面
      </button>
      {hint && (
        <span className="install-hint" role="status">
          点浏览器底部的「分享」，选择「添加到主屏幕」。
        </span>
      )}
    </span>
  );
}
