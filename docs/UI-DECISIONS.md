# UI decisions log

A short, dated log of UI decisions that were thrashed and need to settle.
Pair with `docs/DESIGN.md` (which is the timeless spec) — this file is
the running record of "we tried it, here's what stuck, leave it alone."

## Frozen UI decisions (do not re-litigate without owner sign-off)

These decisions oscillated multiple times in the 2026-04-27 → 2026-05-06
window — 18 `feat(ui)` commits in 8 days flipped them, sometimes the
same day. PR-D froze the current state. Hands off until **2026-05-20**
to give the current state at least two weeks of usage before the next
revisit.

- **Header height**: `h-11 md:h-12`. Don't denser, don't taller.
- **HomePage hero**: keeps the search field + "browse courses" headline.
  Don't remove.
- **Footer surface**: `bg-background/95` (matches header `bg-background/90`).
  Don't `bg-muted`, don't add backdrop-blur.
- **Logo size**: `text-sm md:text-base`. Don't bump.
- **Avatar button size**: `h-7 w-7` in nav. Don't shrink, don't grow.
- **`header.manage` vs `header.manageCourses` / `header.admin` vs
  `header.adminPanel`**: same destination, two keys on purpose — compact
  label for the desktop bar, verbose label for the mobile sheet. Don't
  unify them. (Code comments at the call-sites in
  `frontend/src/components/layout/Header.tsx` say the same.)

If a redesign of any of these is needed, open an issue with screenshots
and rationale — don't ship a same-day "polish" commit. The change must
state which decision it overrides and why two weeks of usage data
support the change.

## Frozen icon system (see DESIGN.md "Icons")

DESIGN.md is the source of truth, but for emphasis: lucide sizes are
**14 / 16 / 20 / 24** — nothing else. `strokeWidth={1.75}` on every
icon, every tier. Decorative icons get `aria-hidden="true"`; icons that
are the sole content of a button must give the button an `aria-label`
instead.

The 14px (`h-3.5 w-3.5`) tier was retroactively documented in PR-D
because it had spread to ~50 callsites organically before being formal.
It's the **footnote** tier — inline metadata badges, dismiss `X` in
compact banners, the avatar fallback in the `7×7` profile button. Never
on primary action buttons or page-header icons.

## Design polish wave — May 2026, owner-approved override

The "do not re-litigate" freeze above expires 2026-05-20, but on 2026-05-12 the
project owner approved a design polish wave that overrides specific elements of
the freeze earlier than that date.

**Approved overrides (effective 2026-05-12):**

- Aesthetic direction shifts from strict editorial to "editorial + expressive
  moments" (see `docs/DESIGN.md` for the formal rules and what counts as an
  expressive moment).
- `motion` library (formerly `framer-motion`) is added as a documented exception
  to the four-check rule in `DESIGN.md`.
- Page-by-page polish PRs are allowed before 2026-05-20 because they fall under
  the approved wave, not a same-day flip.

**Still frozen (do not change without explicit re-sign-off):**

- Header height `h-11 md:h-12`
- HomePage hero search field + headline
- Footer surface `bg-background/95`
- Logo size `text-sm md:text-base`
- Avatar button size `h-7 w-7`
- `header.manage` vs `header.manageCourses` key split
- Lucide icon size tiers 14 / 16 / 20 / 24 + `strokeWidth={1.75}`

These remained frozen because the polish wave is about motion, color, and
micro-interactions — not geometry. Geometry stays stable through the wave so
that motion lands on a stable scaffold instead of a moving one.
