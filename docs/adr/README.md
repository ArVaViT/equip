# Architecture Decision Records

This directory captures the **why** behind decisions that cross module
boundaries or are hard to discover from the code alone. Each ADR is a
self-contained Markdown file in numbered order.

Read these before touching the systems they describe — the code may
look like it could be simpler, but an ADR usually explains why the
simpler shape was rejected.

## Index

Numbering starts at 010 because ADR-001 to ADR-009 were written in a
private planning repository before this one was public; ADR-010 was the
first moved here (#236), and the sequence continued from it.

| # | Title | Status |
|---|-------|--------|
| [010](0010-cohorts-as-top-level-entities.md) | Cohorts as top-level admin entities | Accepted (2026-05-13), amended 2026-08-27: rosters belong to the `director` role |
| [011](0011-tailwind-v4-oklch-migration.md) | Tailwind v4 + OKLCH migration — not doing it | Superseded (2026-08-24) |
| [012](0012-invitations-notifications-and-one-way-out.md) | Invitations, notifications, and one way out of the building | Proposed (2026-09-12) |
| [013](0013-a-registry-decides-who-signs-what.md) | A registry decides who signs what, and which edits cost a signature | Accepted (2026-09-17) |

## Format

Loosely based on [Michael Nygard's ADR template](https://github.com/joelparkerhenderson/architecture-decision-record/blob/main/locales/en/templates/decision-record-template-by-michael-nygard/index.md).
Each file:

```
# ADR-NNNN: Short title

- **Status**: Proposed | Accepted | Deprecated | Superseded by ADR-XXXX
- **Date**: YYYY-MM-DD
- **Decision-makers**: (initials / handles)

## Context
What problem are we solving? What constraints apply?

## Decision
What did we choose? In one sentence at the top, with detail below.

## Consequences
What becomes easier? What becomes harder? What did we explicitly
defer?

## Alternatives considered
What else did we look at, and why did we reject it?
```

## When to write an ADR

- A new feature that changes the data model in a way other features
  must accommodate (e.g., adding a join table that ties existing
  entities together).
- A choice that another contributor might reasonably reverse without
  knowing the trade-offs ("why not just use Alembic for migrations?").
- A "no" you want to remember — declined ideas with a documented reason
  prevent re-litigation.

If you find yourself writing a long code comment explaining a
non-local decision, it probably belongs in an ADR instead.
