import { Component, type ReactNode } from "react"
import { datadogRum } from "@datadog/browser-rum"
import i18n from "@/i18n/config"
import { reloadOnceFor } from "@/lib/staleChunkRecovery"

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  override componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack)
    // Forward to Datadog RUM with the React component stack attached as
    // context. datadogRum.init() is a no-op when VITE_DATADOG_* env vars
    // aren't set, and addError silently drops the call if init never ran,
    // so this is safe unconditionally.
    datadogRum.addError(error, {
      componentStack: info.componentStack,
    })

    // Auto-recover from stale-chunk errors after a deploy: an open tab
    // holds the OLD index.html with references to chunk hashes Vercel no
    // longer serves, and any lazy() route navigation throws "Failed to
    // fetch dynamically imported module". A full reload pulls the fresh
    // index.html with current chunk hashes and the user is back to work.
    // The loop guard (in `reloadOnceFor`) prevents an offline user from
    // bouncing forever, and is shared with `installPreloadErrorRecovery`'s
    // `window` listener for the same-shaped failures that never reach here.
    reloadOnceFor(error)
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  override render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback
      return (
        <div className="flex flex-col items-center justify-center min-h-[50vh] p-8 text-center">
          <div className="h-16 w-16 rounded-full bg-destructive/10 flex items-center justify-center mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-destructive-ink" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold mb-2">{i18n.t("errors.boundary.heading")}</h2>
          <p className="text-sm text-ink-muted mb-4 max-w-md">
            {i18n.t("errors.boundary.body")}
          </p>
          <div className="flex gap-3">
            <button
              onClick={this.handleReset}
              className="inline-flex items-center justify-center rounded-md -strong bg-surface px-4 py-2 text-sm font-medium hover:bg-heritage hover:text-ink transition-colors"
            >
              {i18n.t("errors.boundary.tryAgain")}
            </button>
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center justify-center rounded-md bg-brand px-4 py-2 text-sm font-medium text-brand-foreground hover:bg-brand/90 transition-colors"
            >
              {i18n.t("errors.boundary.refresh")}
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
