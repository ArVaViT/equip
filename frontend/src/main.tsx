import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import ErrorBoundary from './components/ErrorBoundary'
import { initDatadogRum } from './lib/datadog'
// Configures i18next; catalogs are per-locale lazy chunks. We await
// `i18nReady` below so the very first render already has the active
// locale's translations — no key flicker on cold start.
import { i18nReady } from './i18n/config'
// Literata sets Russian, English and biblical Greek in one family; Fraunces —
// which this product used until 2026-08-12 — contains zero Cyrillic glyphs, so
// every Russian heading was silently falling back to Georgia while every
// English one rendered in Fraunces. Two languages, two typefaces, one page.
// See equip-design/decisions/001-typography.md.
import '@fontsource-variable/literata/index.css'
import '@fontsource-variable/golos-text/index.css'
import './index.css'

// Initialize monitoring before React mounts so early boot errors
// (bad env vars, missing #root, etc.) get captured. No-op when the
// VITE_DATADOG_* env vars are unset (local dev without credentials).
initDatadogRum()

const rootEl = document.getElementById('root')
if (!rootEl) {
  throw new Error('Root element #root not found in DOM')
}

// Gate the first render on the active locale's catalog so the initial
// paint is already translated. If the catalog fetch fails (offline,
// CDN hiccup) we render anyway — untranslated keys beat a blank page.
void i18nReady
  .catch(() => {
    /* degrade: render with whatever resources resolved */
  })
  .then(() => {
    ReactDOM.createRoot(rootEl).render(
      <React.StrictMode>
        <ErrorBoundary>
          <App />
        </ErrorBoundary>
      </React.StrictMode>,
    )
  })
