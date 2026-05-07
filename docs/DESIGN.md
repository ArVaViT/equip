# Design Guide

Single source of truth for how this app looks and behaves. Short on purpose.

## Aesthetic

**Editorial, not playful.** Think Linear / Stripe docs / The Atlantic, not Duolingo.
High contrast, confident typography, minimal colour, tight spacing, zero gratuitous
gradients or shadows.

## Tokens

All colours live in `frontend/src/index.css` as CSS variables in OKLCH. No
component ever uses a raw Tailwind palette class (`bg-blue-500`, `text-rose-600`).
If you need a colour, use a semantic token or add one.

Semantic set (light + dark):

| Token               | Use                                 |
|---------------------|-------------------------------------|
| `background` / `foreground` | Page surface + body text    |
| `muted` / `muted-foreground` | Secondary surface + captions |
| `card` / `card-foreground`   | Elevated surfaces            |
| `popover` / `popover-foreground` | Overlays                 |
| `primary` / `primary-foreground` | Brand + primary actions  |
| `accent` / `accent-foreground`   | Highlight (rare, academic gold) |
| `destructive` / `destructive-foreground` | Danger only      |
| `border` / `input` / `ring`  | 1px lines, form borders, focus |

Extra statuses (added as needed): `success`, `warning`, `info`. Always paired
with a `-foreground`.

## Typography

One scale, one serif, one sans.

- **Serif (`Fraunces`):** page titles (H1, H2), chapter reader body.
- **Sans (`Inter`):** everything else.
- **Scale:** `32 / 24 / 18 / 16 / 14 / 13` px. No `text-[Npx]` arbitrary values.
- **Weights:** 400 body, 500 UI, 600 emphasis, 700 display. No 800/900.

## Spacing, radius, elevation

- **Radius:** `rounded-md` (6px) default. `rounded-lg` only for dialogs.
  No `rounded-2xl`, no `rounded-3xl`.
- **Borders:** 1px `border-border` everywhere. No double borders.
- **Shadows:** overlays only (dialog, popover, dropdown). Cards are flat with
  a border. No `shadow-lg` on static content.
- **Spacing:** Tailwind scale, multiples of 4. Page padding `p-6` desktop,
  `p-4` mobile. Cards `p-5`.

## Icons

- `lucide-react` is the **only** icon library.
- Sizes: `14` (footnote / inline metadata), `16` (inline), `20` (buttons),
  `24` (headers). Nothing else.
  - `14` (`h-3.5 w-3.5`) — footnote tier. Use for inline metadata badges
    (e.g. `CourseCard` ratings/duration), inline-text adornments (e.g. the
    footer support `Mail` icon, status dots, dismiss `X` in compact banners,
    and the avatar fallback in the `7×7` profile button). Don't use it on
    primary action buttons or page-header icons.
  - `16` (`h-4 w-4`) — default inline icon (next to body-size labels).
  - `20` (`h-5 w-5`) — icon-only buttons + leading icons in primary actions.
  - `24` (`h-6 w-6`) — section headers and empty-state hero icons.
- `strokeWidth={1.75}` on every icon, every size — including the 14px tier.
- Mark icons that are decoration-only with `aria-hidden="true"`. Icons that
  are the sole content of a button must instead carry an `aria-label` on
  the button (or an `<span class="sr-only">`) — never both `aria-hidden`
  and no accessible name.
- Never emoji as UI.

## One pattern per job

| Job                    | Component / library |
|------------------------|---------------------|
| Confirm destructive    | `useConfirm()` → Radix `AlertDialog` |
| Toast                  | `sonner`, bottom-right |
| Form                   | `react-hook-form` + `zod` + shadcn `Form` |
| Table                  | `@tanstack/react-table` + `<DataTable>` |
| Overlay (menu)         | Radix `DropdownMenu` |
| Overlay (info)         | Radix `Popover` |
| Overlay (hint)         | Radix `Tooltip` |
| Drawer / mobile nav    | Radix `Sheet` |
| Command palette (⌘K)   | `cmdk` |
| Editor                 | `@tiptap/*` |
| Drag & drop            | `@hello-pangea/dnd` |
| Virtualisation         | `react-window` |
| Validation             | `zod` |
| HTTP                   | `axios` |
| Sanitise HTML          | `dompurify` |

If a job is missing from this table, add it here before installing anything.

## Inline editing (no "Edit" buttons)

Titles, descriptions, covers — edited **in place** via a hover pencil icon, not a
separate page or modal. One component `<InlineEdit>` lives in
`frontend/src/components/patterns/`. Rules:

- Pencil appears on hover; on keyboard focus it is always visible.
- `Esc` / click outside cancels; `Enter` / ✓ saves (multiline: `Cmd+Enter`).
- Cover: hover overlay with `Replace` / `Remove`, drag-drop a file to replace.
- Never open a modal just to change one field.

## Page states

Every data view must handle three states:

1. **Loading:** a skeleton that matches final layout. `<PageSpinner>` only
   when a skeleton is impossible.
2. **Empty:** `<EmptyState icon title action>`. No "No data" plain text.
3. **Error:** `<ErrorState onRetry>`. No silent failures.

## Banned patterns

- `window.prompt`, `window.alert`, `window.confirm`
- Raw palette classes: `(bg|text|border|ring|from|to|via)-(red|blue|green|amber|emerald|violet|rose|sky|indigo|lime|pink|yellow|cyan|teal|orange|purple|fuchsia)-\d+`
- Arbitrary pixel text size: `text-[Npx]`
- Inline `style={{ ... }}` with colours or sizes (positioning is fine)
- Emoji as UI
- Hand-rolled overlays (dialog, popover, tooltip, dropdown)
- A second toast / confirm / form / icon / date library

These get ESLint-enforced one by one as each wave removes existing violations.
Don't add rules before the cleanup.

## Adding a library

Four-check rule:

1. No shadcn/Radix/Tailwind solution exists.
2. Saves ≥ 300 lines of code we'd otherwise write.
3. Actively maintained (release in last 6 months).
4. Adds ≤ 20 KB gzip to initial bundle.

If any check fails, don't add it.

## Dark mode

Every new UI must be verified in dark mode before the PR lands. If a token
doesn't look right in one theme, fix the token — don't branch on `.dark`.

## Accessibility

- Every icon-only button has `aria-label`.
- Focus rings via `ring` token, never hidden.
- Text contrast ≥ 4.5:1 for body, ≥ 3:1 for large.
- Keyboard reachable: every action must be reachable without a pointer.
- Run axe-core locally before a release.
