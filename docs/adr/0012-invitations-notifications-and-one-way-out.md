# ADR-012: Invitations, notifications, and one way out of the building

- **Status**: Proposed (2026-09-12)
- **Date**: 2026-09-12
- **Decision-makers**: @ArVaViT (owner), @claude (Equip agent)

## Context

Equip has to reach people who do not have an account yet. The first
live course made that concrete: five people are to be invited onto
"Preaching Course I", none of them has signed up, and the course they
are being invited to is not something an invitation can express today.

Four things exist and none of them meet.

**Invitations** (`invitations`, `invitation_service.py`) carry an
organization and a role. The token is a bearer secret with a seven-day
life, single-use, guarded by a conditional `UPDATE ... WHERE
status='pending'` — that part is sound and stays.

**Notifications** (`notifications`, `notification_service.py`) are a
bell and nothing else. A notification stores a recipe (catalog key plus
params) and renders in the reader's language at read time, which is the
right shape. Seven kinds exist. Two static guards enforce the shape: a
kind must be a literal or a module constant, and no text may be written
at the call site.

**Auth mail** goes Supabase Auth → `send-email` edge function → Resend,
with a signed hook payload, four types, four languages, and a test that
forbids the retired palette.

**Invitation mail** goes backend → Resend directly, because an
invitation is not an Auth event. It carries a second copy of the brand
styling — the copy that was retired — a second string catalog, and a
second way of reaching Datadog.

### What is actually broken

Five defects, each confirmed by reading the code or querying
production, not by inference:

1. **Accepting an invitation does not put the person in the school.**
   `invitation_service.py:303` writes exactly one field:

   ```python
   db.query(User).filter(User.id == current_user_id).update({User.role: invitation.role})
   ```

   `organization_id` stays `NULL`. The invited teacher gets the role and
   then fails `organization_of()` with 403 on every organizational
   route; the invited student cannot see an institute course or enroll
   in it. The invitation row has the organization — it is simply never
   copied.

2. **The role is overwritten downward.** The same statement demotes a
   director who accepts a student invitation.

3. **Deduplication does not know about organizations.** The lookup
   matches `(email, role, pending)` with no organization filter, and
   the partial unique index behind it is `(email, role) WHERE
   status='pending'` — also global. School B inviting a person who has
   a pending invitation from school A gets back **A's row** and sends
   mail carrying A's token.

4. **A signed-in client can rewrite its own `organization_id`.**
   `authenticated` holds table-level `UPDATE` on `profiles`;
   `profiles_update_own_safe_fields` allows the row; and
   `profiles_protect_immutable_fields` guards only `id`, `role`,
   `email`, `created_at`. Verified against production inside a rolled
   back transaction: the write passed policy and trigger and failed
   only on the foreign key, which a real organization id satisfies.
   `deactivated_at` and `onboarding_completed_at` are equally
   unguarded — the first means a deactivated account can restore
   itself.

5. **Delivery is invisible.** No record of a sent message exists in the
   database. Bounces, complaints and spam folders are unobservable, and
   there is no unsubscribe anywhere. Documented as accepted debt; it
   stops being acceptable the moment mail is sent on a schedule rather
   than in reply to an action.

### What the platform cannot express at all

- **A time zone.** Neither `profiles` nor `org_settings` has one;
  greps over the models and over the live schema come back empty. This
  is why the event notification deliberately does not name a date. A
  reminder that says "tomorrow at 8pm" is not writable today.
- **A preference.** No channel setting, no digest, no opt-out. The only
  filter on a recipient is "not deactivated".

## Decision

### 1. One invitation, with a scope

An invitation stays one table and one token. It gains a `scope` and the
target that scope needs:

| scope | new columns used | what accepting does |
|---|---|---|
| `platform` | — | account exists; nothing else |
| `organization` | `organization_id` | membership + role |
| `course` | `organization_id`, `course_id` | membership + role + enrollment |

`scope` is a column, not an inference from which fields are null:
"course invitation whose course was deleted" must stay a course
invitation that fails loudly, not silently become an organization
invitation.

The uniqueness key moves to `(organization_id, email, role, course_id)
WHERE status = 'pending'`, and the service lookup gains the same
filter. Two schools stop colliding, and the same school inviting the
same person to two courses stops being a conflict.

**Rejected:** a separate `course_invitations` table. It would double
the token vocabulary, the preview route, the accept funnel, and the
audit shape for one extra column.

### 2. Accepting is one transaction with the whole consequence

`accept_invitation` becomes explicit about everything it changes:

```
status pending → accepted          (already guarded, unchanged)
role   = max(current, invited)     (never downward)
organization_id = invitation.organization_id  (when the scope has one)
enrollment      = enroll_user_in_course(...)  (when the scope is course)
audit           = one row naming all of the above
```

Role never moves down: a director accepting a student invitation keeps
being a director and still gets the membership and the enrollment. The
ordering is `TEACHING_ROLES` plus student, and it lives next to
`can_teach()` rather than being re-derived.

Enrollment reuses `enroll_user_in_course` — it already takes an
arbitrary `user_id`, is idempotent on `(user, course, cohort)` and
catches the race. It has had exactly one caller (self-enrollment); this
is the second. No new insert path, and specifically **not** the cohort
path, which would drag in windows, capacity and status for a course
that may have no cohort at all.

An invitation to a course the inviter no longer owns, or to a course in
another organization, is refused at **creation**, and again at
**acceptance**, because seven days pass in between.

### 3. One mail layer

One module renders and sends every message the backend originates:
one set of brand constants, one catalog, one timeout, one redaction
policy (domain, never the address), one place that knows `FROM`.

The edge function keeps its own copy of the *styling* — it cannot
import Python — but stops being a second source of *decisions*: the
palette test that exists there is mirrored on the backend side, so the
retired colours cannot come back through the door that is not watched.

Sending never blocks the action that caused it. That is today's
behaviour and it is right; what changes is that a failure stops being
invisible (§5).

### 4. A notification is an event with channels

The bell stays exactly as it is. What changes is that each kind
declares, in one table next to the kind itself, whether it is also
worth an email:

| kind | bell | mail |
|---|---|---|
| `assignment_graded` | yes | no |
| `new_announcement` | yes | no |
| `new_event` | yes | **yes** |
| `event_rescheduled` | yes | **yes** |
| `certificate_approved` | yes | **yes** |
| `certificate_rejected` | yes | no |
| `retake_requested` | yes | no |
| `lesson_reminder` (new) | yes | **yes** |

The rule behind the column: mail is for what a person cannot afford to
discover late, and for nothing else. A graded assignment waits; a
session that starts in an hour does not.

Both static guards keep holding: the kind stays a literal at the call
site, the text stays in the catalog in four languages, and the mail
body renders from the same recipe as the bell, so the two can never
say different things.

Every email carries `List-Unsubscribe` and a footer link, and a person
can turn off each mailable kind. Transactional mail — invitation,
password, confirmation — is not in that list and has no opt-out.

### 5. Delivery becomes visible

A `message_deliveries` row is written for every message the platform
sends: recipient id where known, address domain, kind, locale,
provider message id, status. A Resend webhook — signed, same library
the Auth hook already uses — moves that row through
`sent → delivered → bounced | complained`.

This is the smallest thing that converts "the email did not arrive"
from a conversation into a query, and it is a precondition for §6, not
a nice-to-have beside it.

### 6. Reminders are scheduled, and the school owns the clock

`org_settings` gains `timezone` (IANA, `America/Indiana/Indianapolis`
for UCOAT). Reminders fire per course event at two offsets — 24 hours
and 1 hour — resolved in the school's zone, and the reminder text may
finally name the time because now there is a zone to name it in.

A per-person override belongs on `profiles` later; the school-level
zone is what the first four schools actually need and it costs one
column.

The worker follows the existing shape exactly: `POST /internal/...`
plus a `GET` alias for Vercel Cron, `require_worker_secret`, a pure
`_run_one_tick(db)` for tests, a typed response that says what it did.
A `(event_id, offset)` unique row is what makes a reminder exactly-once
rather than "once per cron tick that happens to fall inside the
window".

### 7. The security fixes are not optional and not last

Defect 4 ships first and separately: `organization_id`,
`deactivated_at` and `onboarding_completed_at` join the immutable set
in `profiles_protect_immutable_fields`, with an assertion in
`rls_assertions.sql` for each. It is a self-contained migration that
does not wait for any of the above.

Public token surfaces (`/invitations/token/{token}`) get a Vercel WAF
rule, because the in-memory limiter is per-worker and this endpoint
answers questions about strangers' email addresses.

Nothing renders unescaped into an email body — today's f-strings hold
only system-generated URLs, which is true and fragile, and a personal
note from the inviter is exactly the feature that would break it.

## Consequences

**What gets better.** An invited person lands where they were invited —
in the school, on the course — instead of in a role with no home. Two
schools stop sharing an invitation namespace. A signed-in account stops
being able to walk into another school's catalog. Mail looks like one
product, arrives in the reader's language, and can be answered for when
it does not arrive.

**What it costs.** Three migrations (invitation scope and unique key,
`message_deliveries` and reminders, profile immutability); one new
worker and one new cron entry; a preferences surface; roughly twenty
new catalog keys in four languages each. The accept path becomes the
most consequential transaction in the product and needs tests to match:
downgrade, cross-organization, deleted course, double click, and the
race between two devices.

**What we are choosing not to do.** No per-person time zone yet. No
digest — every mailable event is its own message until volume argues
otherwise. No second delivery provider. No in-app real-time push: the
bell keeps polling, which is adequate at this size and honest about it.

**What stays true.** The token is a bearer secret, so `invitations`
keeps zero RLS policies and every read goes through the backend.
Delivery failure never fails the action. The host in a link comes from
configuration, never from a request header.

## Order of work

1. Profile immutability + RLS assertions. Ships alone, today.
2. Invitation scope, unique key, and the full accept transaction.
3. One mail layer, with the invitation as its first caller and the
   palette guard mirrored.
4. `message_deliveries` + Resend webhook.
5. Notification channels, preferences, unsubscribe.
6. `org_settings.timezone`, reminder worker, cron, monitor.

Steps 1–3 are what the five people waiting for "Preaching Course I"
actually need. Steps 4–6 are what keeps the next fifty from being a
support conversation.
