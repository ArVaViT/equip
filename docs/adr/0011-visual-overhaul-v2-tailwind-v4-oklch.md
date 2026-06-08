# ADR-0011: Visual overhaul v2 — Tailwind v4 + OKLCH tokens

- **Status**: Partially executed (as of 2026-06-08). The semantic-token
  bridge work shipped iteratively on Tailwind **v3** (visual-overhaul-v2,
  Waves 1–16). The headline decision — the Tailwind **v4 + `@theme`**
  migration and the OKLCH palette cutover (Wave 9) — is still **pending**:
  Tailwind is `^3.x`, `tailwind.config.js` is present, and `index.css`
  tokens are HSL. Treat the "10-wave" roadmap below as superseded by the
  shipped v3 bridge path; the v4/OKLCH swap remains the open work.
- **Decision-makers**: @ArVaViT
- **Successor to**: the implicit "v1" design system pinned in
  `docs/DESIGN.md` (Tailwind v3 + hex tokens + ad-hoc semantic
  classes).

## Context

The current design system was assembled iteratively as the product
grew. Three pressure points justify a planned overhaul rather than
another incremental wave:

1. **Token sprawl.** Hex values live in
   `tailwind.config.js`, in CSS variables in `index.css`, and in a
   handful of component-local `cn()` calls. The "Card hover at
   `bg-foreground/40`" rule is in memory because it has no single
   source of truth in code. Every new contributor (and every
   AI-assist) has to be told it.
2. **Dark mode fragility.** A few surfaces still ship colors that
   look fine in light and crush to unreadable in dark. The audit
   in `docs/contrast-audit.md` calls them out one by one — that's
   how we know the structure isn't catching them.
3. **Tailwind v4 + OKLCH lands the upgrade path.** Tailwind v4
   moves the theme to `@theme` CSS custom properties (no JS config),
   which closes the "tokens live in 3 places" problem by giving us
   exactly one. OKLCH gives us perceptually-uniform color math,
   which makes dark-mode derivation a calculation rather than a
   hand-picked second palette.

## Decision

Migrate the frontend to **Tailwind v4 + shadcn CSS-first config +
OKLCH-keyed tokens** in 10 ordered waves over multiple PRs. Each
wave is independently shippable; no single wave is allowed to break
production. The waves are listed below as the canonical roadmap so
contributors can pick up partway.

### The 10 waves

| # | Wave | Touches | Done when |
|---|------|---------|-----------|
| 1 | **Foundation install.** Add Tailwind v4 alpha alongside v3 (no swap yet). Introduce `@theme` block in `index.css` with the existing palette mirrored, plus a sentinel test asserting the OKLCH conversions resolve to the same on-screen colors as v3 within ΔE ≤ 1. | `package.json`, `index.css`, new vitest snapshot | Tailwind v4 installs cleanly, v3 still runs, OKLCH sentinel passes |
| 2 | **Semantic tokens.** Introduce `--color-surface`, `--color-surface-elevated`, `--color-ink`, `--color-ink-muted`, `--color-accent` etc. Map them to the existing palette. No component touched yet. | `index.css` only | Tokens resolvable; visual snapshot unchanged |
| 3 | **Card + Button.** Migrate the two most-used primitives to semantic tokens. Both have existing tests so regressions surface fast. | `card.tsx`, `button.tsx` + Storybook stories | Both render identically in light/dark; jest-axe still clean |
| 4 | **Form primitives.** Input, Label, Select, Checkbox, Radio. Same drill. | `input.tsx`, `label.tsx`, `select.tsx`, `checkbox.tsx`, `radio-group.tsx` | Forms work; existing form tests pass |
| 5 | **Surfaces.** Modal, AlertDialog, Sheet, Popover, Tooltip. | `alert-dialog.tsx`, `dialog.tsx`, `popover.tsx`, `tooltip.tsx` | All overlay surfaces look right; existing Radix tests pass |
| 6 | **Editorial primitives.** Badge, StatCard, EmptyState, ErrorState, PageHeader. | Components listed in `docs/COMPONENTS.md` | Editorial pages render identically; visual diff on storyboard pages clean |
| 7 | **Rich text + media.** TipTap editor surface, BlockRenderer, Callout, Toggle, table styling, code-block highlighting. | `editor/` + `BlockRenderer.tsx` + `lib/callout-toggle.ts` | Chapter view + editor look identical in both themes |
| 8 | **Pages: student golden path.** Catalog, course detail, chapter view, quiz taker, certificate. | `pages/Course/*`, `pages/Quiz/*`, `pages/Certificate/*` | E2E student path passes; visual diff clean |
| 9 | **Pages: teacher golden path.** Course editor, module editor, chapter editor, quiz editor, grading queue, gradebook. | `pages/Teacher/*` | E2E teacher path passes |
| 10 | **Decommission v3.** Delete `tailwind.config.js`, drop the v3 dep, remove the dual-import guard, delete the OKLCH sentinel test (its job is done). Document the new system. | `package.json`, `tailwind.config.js`, `docs/DESIGN.md` | v3 is gone; final visual diff clean across every page |

### Per-wave gates

Every wave PR must:

1. Land its Vitest + jest-axe assertions green.
2. Land a screenshot of each touched component in light and dark mode in the PR description.
3. Show no regression on the Playwright a11y suite (`e2e/a11y.spec.ts`).
4. Keep `npm run build` green (the production bundle compiles).

If a wave can't meet the gates, split it. The wave numbers are not
sacred — splitting Wave 3 into "Card alone" and "Button alone" is
fine if either gets noisy.

## Consequences

**Easier:**

- Theme tweaks become a single-file edit (`index.css` `@theme`
  block), with all components picking up the change automatically.
- Dark mode comes for free for every new component built on the new
  tokens — no second palette to hand-pick.
- OKLCH math gives us tools for generating accessible color pairs
  (we know the L\*, so we can solve for the contrast partner).

**Harder:**

- The Tailwind v4 + Vite plugin combo is younger than v3; expect
  rough edges around HMR + build cache invalidation. Pin to the
  latest release rather than `^` so the surprise upgrade window
  is opt-in.
- Reviewing a wave PR means rendering both themes for every
  touched component. Screenshots in the PR aren't optional.

**Deliberately deferred:**

- A Storybook upgrade. The current Vitest + Testing Library
  coverage is enough; adding Storybook on top now would double the
  PR surface area for marginal benefit. Revisit after wave 10.
- A motion / animation token revamp. The current Framer
  Motion usage is small enough that hand-tuning per surface is
  cheaper than introducing a motion vocabulary.

## Alternatives considered

1. **Stay on Tailwind v3 + keep iterating.** Lowest risk, lowest
   reward. Token sprawl gets worse, dark-mode audit grows. Rejected
   because we already pay the cost in design-system drift; v4's
   `@theme` is the lever that closes the gap, and waiting for v4 to
   be stable doesn't reduce migration cost — it only delays the
   benefit.
2. **Hand-roll a CSS-variables design system without Tailwind v4.**
   Doable, but we'd be re-implementing what v4 ships natively.
   Tailwind v4's `@theme` is the same pattern we'd write ourselves,
   just battle-tested. Rejected.
3. **Switch to a non-Tailwind system (Vanilla Extract, Panda, etc).**
   Each has a steeper migration cost (every `cn()` rewritten) for
   roughly equivalent end state. Rejected.

## Tracking

Each wave lands as its own PR with the title
`feat(design): visual overhaul v2 wave N — <topic>`. Wave 1 ships
behind a feature flag (the v4 plugin is dual-installed but no
component imports from it) so a half-finished wave doesn't block
unrelated work. The flag is removed in Wave 10.

The roadmap above is the source of truth; if a wave is split or
re-ordered, update this ADR in the same PR so the next contributor
has a current map.
