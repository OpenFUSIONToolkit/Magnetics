// A per-panel error boundary. Without one, a throw inside any tab's render (a
// malformed node, a missing meta field, Plotly choking on a bad grid) unmounts
// the WHOLE app — React replaces the tree with nothing. Wrapping each tab keeps a
// failure local to that panel and shows why, instead of a blank white screen.
//
// `resetKeys` clears the error when its values change (e.g. the user picks a
// different shot), so a transient bad payload doesn't wedge the panel forever.
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  resetKeys?: unknown[];
  label?: string;
}
interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface it for debugging; the fallback UI is what the user sees.
    console.error("Panel crashed:", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && !sameKeys(prev.resetKeys, this.props.resetKeys)) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div
          className="placeholder"
          style={{ padding: 16, lineHeight: 1.6, color: "var(--text-dim)" }}
        >
          <strong>{this.props.label ?? "This panel"} failed to render.</strong>
          <br />
          {this.state.error.message}
          <br />
          <span style={{ opacity: 0.7 }}>
            Try a different shot or reload; other tabs are unaffected.
          </span>
          <br />
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            style={{
              marginTop: 10, padding: "4px 12px", cursor: "pointer",
              background: "var(--panel-2)", color: "var(--text)",
              border: "1px solid var(--border-2)", borderRadius: 4,
              fontFamily: "inherit", fontSize: "inherit",
            }}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function sameKeys(a?: unknown[], b?: unknown[]): boolean {
  if (a === b) return true;
  if (!a || !b || a.length !== b.length) return false;
  return a.every((v, i) => Object.is(v, b[i]));
}
