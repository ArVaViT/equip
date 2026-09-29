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

All colours live in `frontend/src/index.css` as CSS variables in **HSL**
(`--background: 40 12% 97%`, consumed as `hsl(var(--token))`). ADR-0011
declined the OKLCH migration (superseded 2026-08-24) and the dormant
`tokens-v2.css` that carried it has been deleted; the v2 names
(`bg-surface`, `text-ink`, `border-edge`, …) are aliases onto the HSL
tokens in `styles/tokens-bridge.css`. No
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

- **Serif (`Literata`):** page titles (H1, H2), chapter reader body.
  Georgia leads the fallback stack because its x-height is closest.
- **Sans (`Golos Text`):** everything else. It replaced Inter for its
  Cyrillic (see the comment in `frontend/tailwind.config.js`); Golos has
  no italic and no Greek, both stay in Literata.
- **Scale:** nine rungs, from `frontend/tailwind.config.js` — `text-xs` 12,
  `text-sm` 14, `text-base` 17, `text-lg` 21, `text-xl` 24, `text-2xl` 28,
  `text-3xl` 34, `text-4xl` 42, `text-5xl` 52 px. Body is 17, not 16. Plus
  `text-reading` (18px/1.7) for long-form prose — chapters, essays, anything
  somebody reads rather than scans. Each rung carries its own line-height and
  tracking in the config, so a size is chosen and never tuned at the callsite.
  No `text-[Npx]` arbitrary values, and there is no exception: `text-xs` is
  the floor, below which Cyrillic stops being legible on a mid-range phone.
- **Weights:** 400 body, 500 UI, 600 emphasis, 700 display. No 800/900.
- **Editorial eyebrow:** the tiny uppercase label that sits above a heading
  (e.g. VerseOfTheDayCard, CourseReadinessCard) is `text-xs font-medium
  uppercase tracking-[0.18em] text-ink-muted`. The wide tracking is
  load-bearing — that's what makes it read as an eyebrow rather than a
  shrunk body line. Use the `<Eyebrow>` pattern component
  (`@/components/patterns`) instead of retyping the recipe; its
  `tone="accent"` variant (`tracking-[0.22em] text-accent`) covers the
  first-run / celebration surfaces.

## Spacing, radius, elevation

- **Radius** (2026-09-28, `--radius` 0.625rem): `rounded-md` (8px) for
  controls — buttons, fields, menus; `rounded-lg` (10px) for tiles inside a
  card and for dialogs; `rounded-card` (14px, `--radius-card`) for cards and
  panels. A course cover at thumbnail size (`CourseThumb`) is 5px. No
  `rounded-2xl`, no `rounded-3xl`. Measured against Coursera, Vercel, Linear
  and BibleProject: fields 6–8px and cards 12–16px everywhere; the app had
  6px on everything and read as plain HTML beside the landing.
- **Borders:** 1px `border-border` for controls + dividers. No double borders.
  Cards carry a hairline `border-edge` in the light theme (without it a
  near-white card floats on the warm page) and none in the dark theme (there
  it outlines every card into a grid). That is what `Card` and
  `.surface-card` already do; a call site states only a deliberate frame —
  selected, drop target, hover tint.
- **Shadows** (2026-09-28): cards and panels carry `shadow-card` — warm,
  layered, 4–7% (`hsl(30 10% 12%)`, the page's ink, never black). In the
  dark theme, where a shadow cannot be seen, the same token is a hairline of
  light and a brighter top edge. `shadow-card-hover` is for `lift` only.
  Overlays keep their own shadows. No `shadow-lg` / `shadow-xl` on content.
- **Card/panel surface:** the `Card` primitive or the `.surface-card`
  utility (`rounded-card`, hairline border in light / none in dark,
  `shadow-card`). Hand-built panels use the same three classes.
- **`lift`:** a clickable card rises 2px to `shadow-card-hover` in 200ms —
  only on a real hover (not touch), never under reduced motion, and only on
  things that go somewhere when clicked. A lifting card that does nothing
  is a false promise. Put it on the element that owns the transition; a
  `transition-colors` on the same element out-ranks it and the rise jumps.
- **One-screen pages:** a page that must fit the window on a desktop (the
  dashboard) puts `data-single-screen` on its root, a direct child of
  `main`. The shell then becomes the window and banners above take their
  height from the page. Do not hard-code the header's height in a calc.
- **Page:** the app shell is `.app-canvas` — two faint pools of `--accent`
  at opposite corners, fixed to the window, on a pseudo-element so a phone
  does not repaint it on scroll.
- **Spacing:** Tailwind scale, multiples of 4. Page padding `p-6` desktop,
  `p-4` mobile. Cards `p-5`.

## Motion

Motion is part of the design language, not absent from it. Rules:

- **Library:** `motion` (the package formerly known as `framer-motion`),
  imported as `motion/react`. Documented exception to the 4-check rule in
  "Adding a library" below.
- **Primitives live in `frontend/src/components/motion/`:**
  - `<StaggerChildren>` — orchestrated entrance for list/grid items
  - `<Reveal>` — one block arriving as the reader reaches it (scroll)
  - `<PressFeedback>` — button-style press scale (0.97 default)
  - Reach for these before hand-rolling `motion.div` in a feature file.
- **Easing:** `cubic-bezier(0.22, 1, 0.36, 1)` ("editorial ease") everywhere —
  smooth, no bounce, no overshoot. Spring physics are banned outside drag
  previews and toast slide-ins; both require sign-off.
- **Duration scale:** three values, and only three — 120ms (press feedback),
  200ms (interaction: menus, popovers, state changes), 400ms (panels, route
  movement, scroll reveal). They live in `lib/motion.ts` and mirror the CSS
  tokens exactly; `motion.test.ts` fails if the two drift. This list used to
  name five durations including a 550ms "scroll reveal" that existed in no
  code — a fourth opinion nobody could honour.
- **Reduced motion:** every primitive falls back to instant render under
  `prefers-reduced-motion: reduce`. Hand-rolled motion must do the same — use
  the `useReducedMotion` hook from `motion/react` as the single source of truth.
- **Banned patterns:** auto-playing carousels, marquee, scroll-jacking,
  parallax-on-everything, looping non-decorative animation, bouncy springs on
  navigation, anything blocking interaction during entrance.

**The landing's scene off the landing.** `LandingBackdrop` also runs behind
the sign-in screens (`AuthLayout`) with `ambient`: the leaves fall open from
one stack and drift, at 30fps, weaker than on the landing, with the text veil
behind the form on desktop. The profile header has a drifting sage glow and a
turning ring round the portrait (`profile-glow`, `avatar-halo`). Those are
the app's only looping decorations; both stop under reduced motion.

The existing CSS animation system in `index.css` (`animate-fade-in`,
`stagger-fade-in`, `lift`, `skeleton-shimmer`, `ambient-mesh`,
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
| Form                   | Controlled `useState` + a `zod` schema from `lib/validations/` (pattern: `pages/Auth/Login.tsx`) |
| Table                  | A plain semantic `<table>` (pattern: `pages/Teacher/gradebook/GradeTableTab.tsx`) |
| Overlay (menu)         | Radix `DropdownMenu` |
| Overlay (info)         | Radix `Popover` |
| Overlay (hint)         | Radix `Tooltip` |
| Drawer / mobile nav    | Radix `Sheet` |
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

### Rules (the short list)

- Every icon-only button has `aria-label`. Decorative icons get `aria-hidden="true"`.
- Focus rings via `ring` token, never hidden. Use the standard set:
  `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`.
- Text contrast ≥ 4.5:1 for body, ≥ 3:1 for large. **Verified end-to-end** —
  including translucent overlays — by `frontend/scripts/contrast-audit.mjs`.
  Run `node scripts/contrast-audit.mjs` from `frontend/` for the full table;
  it reads `index.css` directly, so the output is never stale.
- Keyboard reachable: every action must be reachable without a pointer.
- Run axe-core locally before a release.

### Semantic HTML — choose the right element

- **Clickable surfaces:** always `<button type="button">` for actions or
  `<a href>` for navigation. Never `<div onClick>` or `role="button"` on a
  div *if a real button would work*. The only acceptable `role="button" tabIndex={0}` is the dnd drag handle pattern (see `ChapterRow`, `AssignmentItem`,
  `ModulesList`) where a real button would steal the drag.
- **Headings:** every page must have one `<h1>` describing its primary subject.
  Sub-sections use `<h2>` / `<h3>`. **Never** style a `<div>` or `<span>` to
  look like a heading. `InlineEdit` ships an actual `<h1>` / `<h2>` when
  `size="h1" | "h2"` — use it for editable titles.
- **Landmarks:** the authenticated shell renders `<header>`, `<main id="main-content">`, `<footer>`. The first focusable element is a skip link
  pointing at `#main-content`.

### Live regions

- **Toasts** (`sonner`) ship `role="status"` / `role="alert"` already.
- **Loading spinners** (`PageSpinner`) ship `role="status" aria-live="polite"`
  with an accessible label. Always prefer `PageSpinner` over hand-rolled rings.
- **Banners** that may appear mid-session (announcements, error toasts) use
  `role="status" aria-live="polite"`. Critical errors get `role="alert"`.

### Dropdowns and dialogs

- Radix Dialog / AlertDialog already handle focus trap, `role="dialog"`,
  Escape-to-close, focus return. Do NOT rebuild these.
- Custom dropdowns (e.g. `CalloutDropdown` in the editor) MUST wire:
  - `aria-haspopup="menu"` + `aria-expanded` on the trigger
  - `role="menu"` + `aria-label` on the menu container
  - `role="menuitem"` on each entry
  - Escape-to-close keyboard handler
- Custom prompt inputs use the dialog title as the input's `aria-label` —
  the input is the dialog's sole field, so the title IS its label.

### Forms

- Every input has either `<Label htmlFor>` (visible) or `aria-label`
  (icon-only / search). Search inputs MUST set `type="search"`.
- Validation errors are wired via `aria-invalid={!!err}` and
  `aria-describedby={err ? "name-error" : undefined}`, with the error
  rendered as `<p id="name-error" role="alert">`.

### Color contrast — translucent surfaces

The contrast-audit script composites alpha overlays against their base so we
catch cases where the *effective* surface drops below AA. Currently checked:

- `bg-muted/{15,30,40,60}` over page and over card
- `bg-warning/10` (pending-teacher banner)
- `bg-destructive/10` (form error banner)
- `bg-primary/{5,15}` (selected cards, active toolbar buttons)

All current combinations pass AA on both themes. If you add a new low-alpha
overlay token combination, extend the `PAIRS` array in the script and re-run.
