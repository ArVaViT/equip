# Component patterns

The reusable building blocks that make every page in Equip look like the
same product. Reach for these **before** writing new layout markup or
copy-pasting a sibling page's JSX — they encode the rules from
[`docs/DESIGN.md`](DESIGN.md) (spacing, typography, icon stroke widths,
semantic tokens) so callers don't have to remember them.

## Where they live

| Layer | Path | Purpose |
|-------|------|---------|
| **Primitives** (`ui/`) | [`frontend/src/components/ui/`](../frontend/src/components/ui/) | Thin wrappers over shadcn/Radix — `<Button>`, `<Badge>`, `<Card>`, `<Dialog>`, `<DropdownMenu>`, etc. Keep the names and APIs shadcn/Radix expose. |
| **Patterns** (`patterns/`) | [`frontend/src/components/patterns/`](../frontend/src/components/patterns/) | App-level compositions that aren't worth a shadcn install — they encode our spacing, copy, and behaviour, not just the primitives. |
| **Motion** (`motion/`) | [`frontend/src/components/motion/`](../frontend/src/components/motion/) | Entry / hover / press / page-transition primitives over `motion/react`. See [`docs/DESIGN.md` → "Motion"](DESIGN.md#motion). |

Everything in `patterns/` is re-exported from
[`frontend/src/components/patterns/index.ts`](../frontend/src/components/patterns/index.ts);
import from `@/components/patterns` rather than the individual files.

---

## `<Badge>`

[`frontend/src/components/ui/badge.tsx`](../frontend/src/components/ui/badge.tsx)

Inline status pill. **Every** in-line status / role / type label uses
`<Badge>` — there are no other badge-shaped components in the tree.

### Variants

Each variant maps to a semantic colour token from
[`docs/DESIGN.md` → "Tokens"](DESIGN.md#tokens):

| Variant | When to use |
|---------|-------------|
| `default` | Brand-coloured emphasis (rare). |
| `secondary` | Quiet contextual tag. |
| `outline` | Neutral tag with a 1px border, no fill. |
| `destructive` | Loud destructive state (e.g. "Failed", "Rejected"). |
| `success` / `warning` / `info` | Loud status with the matching semantic colour. |
| `muted` / `accent` | Neutral / accent contextual tag. |
| **`successSubtle` / `warningSubtle` / `infoSubtle` / `destructiveSubtle` / `primarySubtle`** | **Default for inline status pills.** Background is the matching colour at ~15% opacity; foreground is the full-strength colour. Reads as "tinted text" rather than "filled chip" — works in dark mode, doesn't dominate a row of data, and matches the editorial aesthetic. |

The *Subtle variants are the design-system answer to "I want a colored
status pill that doesn't shout." Use them for every status that appears
inline next to body text: enrollment status, certificate status,
audit-log event type, role badges in admin tables, quiz pass/fail
indicators.

```tsx
import { Badge } from "@/components/ui/badge"

// Inline status — use a Subtle variant
<Badge variant="successSubtle">{t("certificate.status.approved")}</Badge>
<Badge variant="warningSubtle">{t("certificate.status.pending")}</Badge>
<Badge variant="destructiveSubtle">{t("certificate.status.rejected")}</Badge>

// Loud chip when the badge IS the visual anchor (rare)
<Badge variant="success">{t("course.status.published")}</Badge>
```

### Don't

- Don't build a one-off `<span class="bg-emerald-100 …">` — there are no
  raw palette classes in this codebase ([`DESIGN.md` → "Tokens"](DESIGN.md#tokens)).
- Don't add a new variant without a token to back it. If you need a new
  colour, add a token first, then the variant.

---

## `<StatCard>`

[`frontend/src/components/patterns/StatCard.tsx`](../frontend/src/components/patterns/StatCard.tsx)

The single metric card shared by `ProgressStats`, `TeacherAnalytics`, and
the admin `OverviewStats` row. Use whenever you'd otherwise reach for a
`<Card>` with a label, a big number, and an icon.

### Variants

| Variant | Layout |
|---------|--------|
| `value-leading` (default) | Label + number on the left, dimmer icon top-right. Used for in-page progress / analytics summaries. |
| `icon-leading` | Framed icon on the left, label + number on the right. Used for the admin overview row at the top of a dashboard. |

```tsx
import { StatCard } from "@/components/patterns"
import { Users, Award, BookOpen } from "lucide-react"

<div className="grid grid-cols-2 md:grid-cols-4 gap-4">
  <StatCard label={t("admin.stats.users")}    value={142} icon={Users} variant="icon-leading" />
  <StatCard label={t("admin.stats.courses")}  value={12}  icon={BookOpen} variant="icon-leading" />
  <StatCard label={t("admin.stats.certs")}    value={67}  icon={Award} variant="icon-leading" />
</div>
```

The component already enforces `strokeWidth={1.75}`, the `6×6` icon size,
the `tabular-nums` numeric font feature, and the muted-foreground colour
on the icon. Don't pass an icon className that overrides those.

---

## `<EmptyState>` and `<ErrorState>`

[`patterns/EmptyState.tsx`](../frontend/src/components/patterns/EmptyState.tsx),
[`patterns/ErrorState.tsx`](../frontend/src/components/patterns/ErrorState.tsx)

Two of the three page states every data view must handle
([`DESIGN.md` → "Page states"](DESIGN.md#page-states)). The third
(loading) is a layout-matching `<Skeleton>` — see the `ui/skeleton.tsx`
primitive.

### `<EmptyState>` — "no data yet"

For the legitimate-no-data case: a teacher with no courses, a student
with no certificates, an empty search result. Centred column with
icon / title / optional description / optional action.

```tsx
import { EmptyState } from "@/components/patterns"
import { BookOpen } from "lucide-react"

<EmptyState
  icon={<BookOpen />}
  title={t("courses.empty.title")}
  description={t("courses.empty.description")}
  action={
    <Button asChild>
      <Link to="/courses">{t("courses.empty.browse")}</Link>
    </Button>
  }
/>
```

### `<ErrorState>` — "we tried to load X and failed"

For the recoverable-error case: API 5xx, timeout, network error. Includes
`role="alert"` and the destructive icon colour. Primary action is
typically a retry button; secondary action is typically a "back" link.

```tsx
import { ErrorState } from "@/components/patterns"

if (error) {
  return (
    <ErrorState
      title={t("course.error.loadFailed")}
      description={t("course.error.tryAgain")}
      action={<Button onClick={refetch}>{t("common.retry")}</Button>}
      secondaryAction={<Button variant="outline" asChild>
        <Link to="/courses">{t("common.back")}</Link>
      </Button>}
    />
  )
}
```

### Don't

- Don't render plain "No data" text. Use `<EmptyState>`.
- Don't render a toast for a page-level load failure. Use `<ErrorState>` —
  the user needs the retry affordance in-place, not a transient pop-up.

---

## `<InlineEdit>`

[`patterns/InlineEdit.tsx`](../frontend/src/components/patterns/InlineEdit.tsx)

The "no Edit buttons" pattern. Titles, descriptions, names — edited in
place via a hover-pencil icon, never a separate page or modal.
[`DESIGN.md` → "Inline editing"](DESIGN.md#inline-editing-no-edit-buttons)
is the spec; `<InlineEdit>` is the implementation.

### Behaviour

- Pencil icon appears on hover. On keyboard focus it's always visible.
- `Esc` or click-outside cancels. `Enter` saves. Multiline mode requires
  `Cmd+Enter` / `Ctrl+Enter` to save (plain `Enter` inserts a newline).
- Empty values are rendered as italic muted-foreground placeholder text.
- While the save promise is in flight, the input is disabled and a
  `Loader2` spinner replaces the check/cancel buttons.

### Sizes

- `h1` — page titles (Fraunces serif, large, semibold).
- `h2` — section titles (Fraunces serif, medium, semibold).
- `body` — descriptions, names, anything in body copy (Inter sans).

### Example

```tsx
import { InlineEdit } from "@/components/patterns"

<InlineEdit
  value={course.title}
  size="h1"
  required
  maxLength={120}
  onSave={async (next) => {
    await api.patch(`/courses/${course.id}`, { title: next })
    refetchCourse()
  }}
/>

<InlineEdit
  value={course.description ?? ""}
  size="body"
  multiline
  placeholder={t("course.description.placeholder")}
  onSave={async (next) => {
    await api.patch(`/courses/${course.id}`, { description: next })
  }}
/>
```

### `<InlineEditCover>`

[`patterns/InlineEditCover.tsx`](../frontend/src/components/patterns/InlineEditCover.tsx)

The cover-image variant of the same pattern. Hover overlay with Replace
and Remove actions, drag-drop a file to replace. Used for course covers
and similar image fields.

### Don't

- Don't open a modal just to change one field. That's a regression of
  the editorial UX the platform has been built around.

---

## `<PageHeader>`

[`patterns/PageHeader.tsx`](../frontend/src/components/patterns/PageHeader.tsx)

The page-level header strip: optional back link, optional cover image,
title slot, optional description, optional meta row (badges, dates,
counters), optional actions cluster on the right.

```tsx
import { PageHeader } from "@/components/patterns"
import { Badge } from "@/components/ui/badge"

<PageHeader
  backTo="/courses"
  backLabel={t("common.backToCourses")}
  title={
    <InlineEdit
      value={course.title}
      size="h1"
      onSave={saveTitle}
    />
  }
  description={
    <InlineEdit
      value={course.description ?? ""}
      size="body"
      multiline
      onSave={saveDescription}
    />
  }
  meta={
    <>
      <Badge variant="successSubtle">{t("course.status.published")}</Badge>
      <Badge variant="outline">{course.module_count} {t("course.modules")}</Badge>
    </>
  }
  actions={
    <>
      <Button variant="outline" onClick={openPreview}>{t("common.preview")}</Button>
      <Button onClick={openPublishDialog}>{t("common.publish")}</Button>
    </>
  }
/>
```

Title and description are `ReactNode`, not `string`, on purpose — most
pages pass `<InlineEdit>` straight in. The header itself doesn't know
whether it's wrapping editable or read-only content.

### Don't

- Don't render a `<h1>` outside `<PageHeader>` unless you're inside a
  legitimately header-less view (auth, error pages).
- Don't put the page H1 in `<Card>` — `PageHeader` already sets the
  correct top margin and width.

---

## `<Modal>`

[`patterns/Modal.tsx`](../frontend/src/components/patterns/Modal.tsx)

Thin wrapper over the shadcn `<Dialog>` with the project defaults baked
in: serif title, `max-w-lg`, `max-h-[85vh]`, scrollable body, the
"closes on backdrop click and escape" behaviour wired up. Use it for any
modal that isn't a confirmation dialog.

```tsx
import { Modal } from "@/components/patterns"

<Modal
  open={open}
  onClose={() => setOpen(false)}
  title={t("cohort.create.title")}
>
  <CohortCreateForm onCreated={() => setOpen(false)} />
</Modal>
```

### When NOT to use `<Modal>`

- **Destructive confirmation** ("Delete this course? It cannot be
  undone.") — use `useConfirm()` from
  `@/components/ui/alert-dialog` instead. That's the AlertDialog path
  and has the destructive button variant + focused copy structure baked
  in. ([`DESIGN.md` → "One pattern per job"](DESIGN.md#one-pattern-per-job).)
- **Single-field edit** — use `<InlineEdit>` instead. A modal for one
  field is a regression of the "no Edit buttons" pattern.

---

## Adding a new pattern

Before creating a new file under `patterns/`:

1. Check that no existing pattern covers the case at a slightly higher
   level of abstraction.
2. Check that the case appears in at least **two** places in the app
   today (or will, with this PR). One-off views don't belong in `patterns/`.
3. Encode the design rules (tokens, typography, icon stroke widths,
   spacing) inside the component so callers don't have to remember them.
4. Add an export to
   [`patterns/index.ts`](../frontend/src/components/patterns/index.ts)
   and a section to this file.

If the new pattern wraps a primitive from shadcn / Radix, put the wrapper
in `patterns/`, not `ui/`. `ui/` stays a thin shadcn mirror.
