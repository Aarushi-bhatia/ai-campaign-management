import { Component, type ReactNode } from "react";

type Props = { children: ReactNode; onClose?: () => void };

/** If one part of the screen fails to draw, it shows a short message instead of blanking the whole app. */
export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="m-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800 shadow-sm">
        <p className="font-medium">This part of the screen couldn't be shown.</p>
        <p className="mt-1 text-xs">{this.state.error.message}</p>
        <button
          onClick={() => { this.setState({ error: null }); this.props.onClose?.(); }}
          className="mt-3 rounded-lg border border-red-200 bg-white px-3 py-1 text-xs hover:bg-red-100"
        >
          {this.props.onClose ? "Close" : "Try again"}
        </button>
      </div>
    );
  }
}
