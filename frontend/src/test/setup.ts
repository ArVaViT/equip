import '@testing-library/jest-dom'

// jsdom doesn't implement IntersectionObserver. Components that read it during
// mount (motion/react useInView, viewport reveal, virtualisation) crash without
// a shim. No-op observe is fine — tests assert rendered children, not paint state.
// Don't `implements IntersectionObserver` here: the lib.dom.d.ts shape grows
// (scrollMargin etc.) and would force us to chase every new field. The runtime
// cast on assignment is the durable boundary.
if (!globalThis.IntersectionObserver) {
  class IntersectionObserverShim {
    readonly root = null
    readonly rootMargin = ''
    readonly thresholds: ReadonlyArray<number> = []
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
    takeRecords(): IntersectionObserverEntry[] { return [] }
  }
  globalThis.IntersectionObserver = IntersectionObserverShim as unknown as typeof IntersectionObserver
}
