import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import ErrorBoundary from './components/ErrorBoundary'
import { initDatadogRum } from './lib/datadog'
// Side-effect import: configures i18next before any component mounts so
// the very first render already has translations available.
import './i18n/config'
import '@fontsource-variable/inter/index.css'
import '@fontsource-variable/fraunces/index.css'
import './index.css'

// Initialize monitoring before React mounts so early boot errors
// (bad env vars, missing #root, etc.) get captured. No-op when the
// VITE_DATADOG_* env vars are unset (local dev without credentials).
initDatadogRum()

const rootEl = document.getElementById('root')
if (!rootEl) {
  throw new Error('Root element #root not found in DOM')
}

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
