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
)
