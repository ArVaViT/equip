# ADR-011: Tailwind v4 + OKLCH migration — not doing it

- **Status**: Superseded (2026-08-24). Proposed 2026-06-02 as a ten-wave
  migration; never started. The design system it wanted to replace was
  rebuilt on Tailwind v3 in August 2026 and is now frozen.
- **Decision-makers**: @ArVaViT

## Context

The original proposal argued three things: tokens lived in three places
(`tailwind.config.js`, CSS variables in `index.css`, ad-hoc `cn()` calls),
dark mode was fragile on a few surfaces, and Tailwind v4's `@theme` block
plus OKLCH color math would close both problems by giving the palette one
home and making dark mode a calculation instead of a second hand-picked
palette.

Two of those three premises stopped being true before the work began.

## Decision

**The migration is off.** Equip stays on Tailwind v3 with HSL semantic
tokens in `index.css`.

Why:

- **The sprawl was fixed without v4.** The August design rebuild moved
  every color to a semantic token and the geometry is frozen — see
  `docs/DESIGN.md` and `docs/UI-DECISIONS.md`. There is one home for the
  palette today; `@theme` would move it, not consolidate it.
- **Dark mode is verified, not hoped for.** `frontend/scripts/contrast-audit.mjs`
  composites translucent overlays against their base and checks every pair
  against the AA thresholds. That guard is what caught the crushed
  surfaces, and it works the same on v3 as it would on v4.
- **The cost was never the palette — it was every `cn()` in the tree.**
  Ten waves of PRs, each requiring both themes rendered per component,
  against a product with no users yet. The benefit is perceptual color
  math the project has not once needed.

OKLCH remains a good idea in the abstract. It is not a good idea to spend
the only maintainer's weeks on it.

## Consequences

- `tailwind.config.js` stays. So does the v3 dependency.
- New components take their colors from the semantic tokens, as they
  already do; nothing about day-to-day work changes.
- If Tailwind v3 stops receiving security updates, this decision gets
  reopened as an upgrade forced by support, not as a design overhaul.
