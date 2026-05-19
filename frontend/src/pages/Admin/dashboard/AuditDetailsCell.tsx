import { useTranslation } from "react-i18next"

interface Props {
  details: Record<string, unknown> | null
}

/**
 * Render the audit-log ``details`` payload as a tight key→value list.
 *
 * The backend writes whichever fields are meaningful per action — for
 * an ``update`` that's typically ``{field: 'title', old: '...', new: '...'}``
 * or a nested object of changed columns; for an ``approve`` it might be
 * the approver id; for ``enroll`` the cohort. We don't try to be
 * exhaustive — we render whatever's there, formatted to be readable
 * inside one cell, and fall back to a dim em-dash when the field is
 * empty (admin reviews scan for "what changed", an empty cell tells
 * them "nothing actionable in the payload" rather than "broken").
 *
 * No dangerouslySetInnerHTML — every value is stringified and rendered
 * as plain text so the audit table can't host stored-XSS payloads.
 */
export function AuditDetailsCell({ details }: Props) {
  const { t } = useTranslation()
  if (!details || typeof details !== "object" || Object.keys(details).length === 0) {
    return <span className="text-muted-foreground/60">—</span>
  }

  const entries = Object.entries(details)

  // Special-case the most common "field/old/new" pattern from
  // service-layer writes: render as "title: 'old' → 'new'" instead of
  // three rows. Pulled in alphabetical order from the keys so we
  // recognise it whether the writer used 'field/old/new' or any of
  // those keys with different casing.
  if (
    entries.length === 3 &&
    "field" in details &&
    ("old" in details || "before" in details) &&
    ("new" in details || "after" in details)
  ) {
    const field = String(details.field ?? "")
    const oldVal = formatValue(details.old ?? details.before)
    const newVal = formatValue(details.new ?? details.after)
    return (
      <div className="flex flex-wrap items-baseline gap-1.5 text-xs">
        <span className="font-medium text-foreground">{field}:</span>
        <span className="font-mono text-muted-foreground line-through">{oldVal}</span>
        <span aria-hidden className="text-muted-foreground/60">→</span>
        <span className="font-mono text-foreground">{newVal}</span>
      </div>
    )
  }

  return (
    <ul className="space-y-0.5 text-xs">
      {entries.map(([key, raw]) => (
        <li key={key} className="flex flex-wrap items-baseline gap-1.5">
          <span className="font-medium text-foreground">{key}:</span>
          <span className="font-mono text-muted-foreground">{formatValue(raw)}</span>
        </li>
      ))}
      {entries.length === 0 && (
        <li className="text-muted-foreground/60">{t("admin.audit.detailsEmpty")}</li>
      )}
    </ul>
  )
}

function formatValue(v: unknown): string {
  if (v === null) return "null"
  if (v === undefined) return "—"
  if (typeof v === "string") {
    if (v === "") return '""'
    // Truncate long strings so a 5KB HTML diff doesn't blow the row
    // height; admins can click into the resource for full context.
    return v.length > 80 ? `${v.slice(0, 80)}…` : v
  }
  if (typeof v === "number" || typeof v === "boolean") return String(v)
  try {
    const json = JSON.stringify(v)
    return json.length > 80 ? `${json.slice(0, 80)}…` : json
  } catch {
    return "[unserializable]"
  }
}
