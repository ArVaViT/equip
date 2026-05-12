import '@testing-library/jest-dom'

// jsdom doesn't implement IntersectionObserver. Components that read it during
// mount (motion/react useInView, viewport reveal, virtualisation) crash without
// a shim. No-op observe is fine — tests assert rendered children, not paint state.
if (!globalThis.IntersectionObserver) {
  class IntersectionObserverShim implements IntersectionObserver {
    readonly root: Element | Document | null = null
    readonly rootMargin: string = ''
    readonly thresholds: ReadonlyArray<number> = []
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): IntersectionObserverEntry[] { return [] }
  }
  globalThis.IntersectionObserver = IntersectionObserverShim as unknown as typeof IntersectionObserver
}
