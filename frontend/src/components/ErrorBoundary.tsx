import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { error: Error | null };

/** 最外层兜底：任何渲染异常都不该让整页变成白屏，至少给出刷新入口。 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("界面渲染失败", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="crash" role="alert">
        <h2>页面出了点问题</h2>
        <p>{this.state.error.message}</p>
        <button className="primary" onClick={() => window.location.reload()}>
          刷新页面
        </button>
      </div>
    );
  }
}