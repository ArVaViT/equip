import '@testing-library/jest-dom'
import i18n, { i18nReady, SUPPORTED_LOCALES } from '@/i18n/config'

// i18n catalogs are lazy per-locale chunks in the app (see i18n/config.ts).
// The unit suite assumes synchronous resources — tests call `t()` right
// after render and flip languages with `await changeLanguage(...)` — so
// preload BOTH catalogs here before any test file runs.
await i18nReady
await i18n.loadLanguages([...SUPPORTED_LOCALES])

// Pin the language for every test file, and pin it here rather than trusting
// detection.
//
// The detector's first source is `localStorage`, and it caches the choice
// there. Under `vitest run` all workers share one localStorage — the store is
// a single file passed to Node — so a test that switches to Russian writes a
// value the *next* file to start reads as its own detected language. Suites
// that assume English (most of them) then fail at random, in whichever file
// happened to boot after that write. It cost two green-then-red gate runs to
// find, because the failing file was never the file that caused it.
//
// English rather than DEFAULT_LOCALE: it is what jsdom's navigator resolves to
// and therefore what the suite has always effectively run under. A test that
// needs another language sets it itself, as several already do.
await i18n.changeLanguage("en")

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
