import { Component, type ReactNode } from "react"
import { datadogRum } from "@datadog/browser-rum"
import i18n from "@/i18n/config"

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

// Patterns that indicate a stale-chunk failure: the user has an old
// index.html in memory pointing at chunk hashes that the latest deploy
// no longer publishes. The fix is to reload — fetching the fresh
// index.html immediately makes the new chunk hashes available.
//
// Each engine spells the failure differently. We match all three so a
// future Vite/Rollup tweak doesn't quietly bring back the bug:
const CHUNK_LOAD_PATTERNS: RegExp[] = [
  /failed to fetch dynamically imported module/i,
  /loading chunk \d+ failed/i,
  /chunkloaderror/i,
]

// Don't loop. If we just reloaded and still hit a chunk error, the
// fix didn't help (e.g. the user is offline) — show the manual UI
// instead of bouncing the page forever.
const RELOAD_FLAG_KEY = "errorBoundary:lastChunkReload"
const RELOAD_COOLDOWN_MS = 60_000

function isChunkLoadError(error: Error): boolean {
  const message = error.message || ""
  return CHUNK_LOAD_PATTERNS.some((re) => re.test(message))
}

function recentlyReloaded(): boolean {
  try {
    const last = parseInt(sessionStorage.getItem(RELOAD_FLAG_KEY) ?? "0", 10)
    return Number.isFinite(last) && Date.now() - last < RELOAD_COOLDOWN_MS
  } catch {
    return false
  }
}

function markReloaded() {
  try {
    sessionStorage.setItem(RELOAD_FLAG_KEY, String(Date.now()))
  } catch {
    // sessionStorage can throw in Safari private mode etc. Worst case
    // we lose the loop guard — better than crashing the recovery path.
  }
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
    // The loop guard prevents an offline user from bouncing forever.
    if (isChunkLoadError(error) && !recentlyReloaded()) {
      markReloaded()
      window.location.reload()
    }
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
            <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8 text-destructive" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold mb-2">{i18n.t("errors.boundary.heading")}</h2>
          <p className="text-sm text-muted-foreground mb-4 max-w-md">
            {i18n.t("errors.boundary.body")}
          </p>
          <div className="flex gap-3">
            <button
              onClick={this.handleReset}
              className="inline-flex items-center justify-center rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              {i18n.t("errors.boundary.tryAgain")}
            </button>
            <button
              onClick={() => window.location.reload()}
              className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
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
