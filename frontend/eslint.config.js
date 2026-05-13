import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'

export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**'],
  },
  {
    files: ['scripts/**/*.{js,mjs,cjs}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.node },
    },
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  reactHooks.configs.flat.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      'react-refresh': reactRefresh,
    },
    rules: {
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      '@typescript-eslint/no-explicit-any': 'error',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/immutability': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      'react-hooks/static-components': 'off',

      // Editorial design guard rails — keep the UI on semantic tokens.
      // See docs/DESIGN.md for the approved vocabulary.
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "Literal[value=/\\b(?:bg|text|border|from|via|to|ring|fill|stroke|divide|placeholder|caret|accent|outline|shadow)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone)-\\d{2,3}\\b/]",
          message:
            'Use semantic tokens (primary / accent / success / warning / info / destructive / muted / border). Raw Tailwind palette classes are banned — see docs/DESIGN.md.',
        },
        {
          // Block `window.alert|confirm|prompt` — `useConfirm()` + AlertDialog + sonner are the shared UX.
          selector:
            "CallExpression[callee.object.name='window'][callee.property.name=/^(alert|confirm|prompt)$/]",
          message:
            'Use <AlertDialog> / useConfirm() / sonner toasts — never native window dialogs.',
        },
        {
          // i18n guard — JSX text content must go through t() (or <Trans>).
          // Triggers on 3+ consecutive Latin or Cyrillic letters between tags;
          // whitespace, punctuation, numbers and short tokens pass through.
          // Suppress for legitimate exceptions (rare) with an inline disable
          // comment + a short reason.
          selector:
            "JSXText[value=/[A-Za-zА-Яа-яЁё]{3,}/]",
          message:
            'Hardcoded user-facing text — wrap in t("namespace.key") instead of inlining (or use <Trans i18nKey="…"> for embedded markup).',
        },
        {
          // i18n guard — string-literal values for user-facing attributes must
          // also be wrapped in t(). Covers aria-label / title / placeholder /
          // alt (the four attributes that screen readers + tooltips read).
          selector:
            "JSXAttribute[name.name=/^(aria-label|title|placeholder|alt)$/] > Literal[value=/[A-Za-zА-Яа-яЁё]{3,}/]",
          message:
            'Hardcoded user-facing attribute value — use {t("namespace.key")} so it translates.',
        },
      ],
      'no-restricted-globals': [
        'error',
        {
          name: 'alert',
          message: 'Use sonner (toast) — never native alert().',
        },
      ],
    },
  },
  // Test files: allow hardcoded English in test names, fixtures, mocks.
  {
    files: ['**/*.test.{ts,tsx}', '**/__tests__/**/*.{ts,tsx}', 'src/test/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-syntax': 'off',
    },
  },
)
