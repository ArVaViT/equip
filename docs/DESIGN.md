# Design Guide

Single source of truth for how this app looks and behaves. Short on purpose.

## Aesthetic

**Editorial, with expressive moments.** Think Linear / Stripe docs / The Atlantic
as the baseline — high contrast, confident typography, tight spacing — but with a
deliberate set of expressive surfaces where motion, gradients, and richer
interactions earn their place: hero areas, CTA buttons, success states, page
transitions, the auth marketing column. The default state of any view is still
quiet and flat. Expressive moments are framed by quiet ones; they don't blanket
the UI.

The expressive direction was formalized on 2026-05-12 (see
`docs/UI-DECISIONS.md`). Before that the rule was "zero gratuitous gradients or
shadows" — that's now scoped to *static / dense* surfaces (forms, tables, data
views). Expressive surfaces have their own rules in "Motion" below.

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

## Motion

Motion is part of the design language, not absent from it. Rules:

- **Library:** `motion` (the package formerly known as `framer-motion`),
  imported as `motion/react`. Documented exception to the 4-check rule in
  "Adding a library" below.
- **Primitives live in `frontend/src/components/motion/`:**
  - `<FadeIn>` — opacity + small Y on mount
  - `<StaggerChildren>` — orchestrated entrance for list/grid items
  - `<Reveal>` — IntersectionObserver-based entrance for scroll-revealed content
  - `<HoverLift>` — card-style hover translation (2px default)
  - `<PressFeedback>` — button-style press scale (0.97 default)
  - `<PageTransition>` — route-keyed `AnimatePresence` crossfade
  - Reach for these before hand-rolling `motion.div` in a feature file.
- **Easing:** `cubic-bezier(0.22, 1, 0.36, 1)` ("editorial ease") everywhere —
  smooth, no bounce, no overshoot. Spring physics are banned outside drag
  previews and toast slide-ins; both require sign-off.
- **Duration scale:** 120ms (press feedback), 280ms (hover, page transitions),
  480ms (mount fade-in), 550ms (scroll reveal). Nothing slower than 600ms,
  nothing faster than 100ms.
- **Reduced motion:** every primitive falls back to instant render under
  `prefers-reduced-motion: reduce`. Hand-rolled motion must do the same — use
  the `useReducedMotion` hook from `motion/react` as the single source of truth.
- **Banned patterns:** auto-playing carousels, marquee, scroll-jacking,
  parallax-on-everything, looping non-decorative animation, bouncy springs on
  navigation, anything blocking interaction during entrance.

The existing CSS animation system in `index.css` (`animate-fade-in`,
`stagger-fade-in`, `motion-safe-hover-lift`, `skeleton-shimmer`, `ambient-mesh`,
`hero-breathe`) stays in place for low-stakes / pre-React content and as a
fallback in legacy callsites. Migration to motion primitives is gradual,
page-by-page, not a big-bang rewrite.

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
| Motion                 | `motion/react` via `components/motion/*` |

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

If any check fails, don't add it. **Documented exceptions:**

- `motion` (~30 KB gzip, fails check 4) — approved 2026-05-12 for the expressive
  direction. The orchestrated entrance, viewport reveal, and `AnimatePresence`
  primitives are not achievable in pure CSS without re-implementing them, and
  the expected migration spans every page across Waves 2-4 of the polish work.

## Dark mode

Every new UI must be verified in dark mode before the PR lands. If a token
doesn't look right in one theme, fix the token — don't branch on `.dark`.

## Accessibility

- Every icon-only button has `aria-label`.
- Focus rings via `ring` token, never hidden.
- Text contrast ≥ 4.5:1 for body, ≥ 3:1 for large.
- Keyboard reachable: every action must be reachable without a pointer.
- Run axe-core locally before a release.
