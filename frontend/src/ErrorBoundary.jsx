import { Component } from "react";

/**
 * Catches render/lifecycle errors in the subtree and shows a recoverable
 * message instead of unmounting to a blank white page.
 */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Render error caught by ErrorBoundary:", error, info);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 text-center shadow-sm">
          <h1 className="text-lg font-semibold text-slate-800">Something broke</h1>
          <p className="mt-2 text-sm text-slate-500">
            The page hit an unexpected error and stopped rendering. Your data is
            safe — reloading usually fixes it.
          </p>
          <pre className="mt-3 max-h-32 overflow-auto rounded bg-slate-900 p-3 text-left text-xs text-slate-100">
            {String(error?.message || error)}
          </pre>
          <div className="mt-4 flex justify-center gap-2">
            <button
              onClick={() => this.setState({ error: null })}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-100"
            >
              Try again
            </button>
            <button
              onClick={() => window.location.reload()}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-500"
            >
              Reload page
            </button>
          </div>
        </div>
      </div>
    );
  }
}
