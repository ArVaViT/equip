import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    css: false,
    // Scope Vitest to ``src/`` so Playwright's ``e2e/*.spec.ts``
    // files don't get sucked in — Playwright's ``test.describe`` API
    // throws when run under Vitest's runner. The default vitest
    // include is ``**/*.{test,spec}...`` which is too broad once we
    // have e2e tests alongside the unit suite.
    include: ['src/**/*.{test,spec}.{js,ts,jsx,tsx}'],
    exclude: ['node_modules/**', 'dist/**', 'e2e/**'],
    // Coverage is opt-in via `npm run test:run -- --coverage`. The defaults
    // here only kick in when that flag is passed (CI), so day-to-day
    // `npm test` watch sessions stay fast.
    coverage: {
      provider: 'v8',
      reporter: ['text-summary', 'lcov', 'json'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.d.ts',
        'src/**/*.test.{ts,tsx}',
        'src/**/__tests__/**',
        'src/test/**',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
    },
  },
})
