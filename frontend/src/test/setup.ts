import '@testing-library/jest-dom'
import i18n, { i18nReady, SUPPORTED_LOCALES } from '@/i18n/config'

// i18n catalogs are lazy per-locale chunks in the app (see i18n/config.ts).
// The unit suite assumes synchronous resources — tests call `t()` right
// after render and flip languages with `await changeLanguage(...)` — so
// preload BOTH catalogs here before any test file runs.
await i18nReady
await i18n.loadLanguages([...SUPPORTED_LOCALES])

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
