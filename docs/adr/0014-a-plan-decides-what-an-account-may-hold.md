# ADR-0014: A plan decides what an account may hold

- **Status**: Accepted (2026-09-20)
- **Date**: 2026-09-20
- **Decision-makers**: VA

## Context

The database is not elastic. Production is 47 MB today, and the shape of
that number is worth reading before capping anything:

| table | size | rows |
|---|---|---|
| `content_versions` | 24 MB | 31 539 |
| `daily_challenge_question_events` | 3.8 MB | 5 101 |
| `translation_jobs` | 648 kB | 1 107 |
| `chapter_blocks` | 344 kB | 116 |
| `courses` | — | 8 live |

A course row is nothing. What a course *carries* is not: every authored
string is stored once per supported locale in `content_versions`, so one
chapter block is four rows there, and the pipeline that fills them leaves
a `translation_jobs` row per field per language on the way. The cost of a
course is therefore roughly the cost of the tree under it, multiplied by
four.

There was already a cap — `MAX_COURSES_PER_TEACHER`, default 50 — and it
had three problems:

1. **It was enforced in one place out of three.** `POST /courses` checked
   it. `POST /courses/{id}/clone`, which copies an entire tree *and* its
   translated strings, did not. Neither did
   `POST /courses/{id}/restore`, so the trash worked as a parking space:
   delete a course, create a replacement, restore the first one, and the
   cap was two courses behind.
2. **It was a number in an env var, not a decision with a shape.** The
   next thing that will happen to this limit is that it stops being the
   same for everyone — a paid tier, a verified organization, an
   exception granted to one school by hand. An `if` in a route has
   nowhere for that to go.
3. **It raised `validation.failed` with a 400**, which says the request
   was malformed. The request was fine; the account was full.

## Decision

**Limits live in one module, as a plan, and every write path that hands an
account one more of something asks that module.**

`backend/app/services/limits.py` holds:

- `LimitKey` — what can be capped. One member today,
  `courses_per_teacher`.
- `BASE_PLAN` — the package every account gets. `courses_per_teacher: 5`.
- `limit_for(user, key)` — resolves the number, most specific first: a
  deployment override (`MAX_COURSES_PER_TEACHER`, now unset by default)
  beats the plan. An organization-level or subscription-level override
  slots in between when there is one to read.
- `assert_within_limit(...)` / `assert_can_own_another_course(...)` — the
  gate, raising the new `plan.limit_reached` code with a 409 and a
  context that names the key, the ceiling and the current count.

Five is the base plan's number because a Bible-school teacher carries a
few subjects at a time, and the abuse cases a cap exists for — a runaway
script, a misread UI — are nowhere near five. Production is comfortably
under it: the busiest teacher holds two courses, the admin three, and
nobody is over the line on the day it ships.

Platform admins are exempt. They seed content and migrate a school's back
catalogue, and a cap that stops that work is a cap that gets raised to
infinity within the week.

## Consequences

**Easier.** Moving the number is one edit in one file, or one env var on
a deployment that differs. Adding a second limit is a `LimitKey` member,
a `BASE_PLAN` entry, and one call at the write path that creates the row.
Giving one school a different ceiling later means teaching `plan_for` to
read something — no route changes.

**Harder / accepted.** The status code for this condition changed from
400 to 409 and the error code from `validation.failed` to
`plan.limit_reached`; anything that switch-matched the old pair has to be
updated (the frontend's union and locale strings are in this change).
The cap is enforced at write time only, so an account that is already
over a lowered limit keeps what it has and simply cannot add — the right
behaviour for a limit that moves, and the reason the pre-existing courses
on production are untouched by the drop from 50 to 5.

**Deferred.** No subscription, no tier table, no per-organization
override column. There is no tier to store yet, and a schema invented
before its first real customer is a migration written twice. The
localized sentence behind `plan.limit_reached` is written for the course
cap, since that is the only key; a second key means teaching that string
to distinguish them by `context.limit_key`.

**Not addressed.** This caps courses, which is the *handle*, not the
weight. If the database is the worry, the weight is `content_versions`,
and the limits that would bound it directly — chapters per course, blocks
per chapter, characters per block — are the obvious next keys in this
same registry.

## Alternatives considered

- **Leave the cap at 50 and just fix the two unguarded routes.** Fixes
  the holes, keeps the number unable to move per account. Rejected: the
  holes and the shape are the same problem, and the fix for both is the
  same module.
- **Store limits in a table now.** Rejected as premature: one plan, no
  customers on a second one, and an applied migration is append-only.
- **Cap per organization rather than per teacher.** Rejected for now: a
  teacher is who creates rows, `courses.created_by` is what the count
  keys on, and an org-level ceiling is the override layer this design
  already has a slot for.
- **Cap the tree (chapters, blocks) instead of the courses.** This is
  the more honest limit and is not rejected — it is the next key, once
  the surface a teacher meets is one they can understand without a
  support conversation.
