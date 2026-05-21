/**
 * Strip the surname off a full name for personal greetings —
 * "Vadym Arnaut" → "Vadym", "Иван Иванович Иванов" → "Иван".
 *
 * Returns ``null`` for null/blank input so callers can fall back
 * to a name-less greeting without having to special-case empty
 * strings.
 *
 * Shared by the dashboard's welcome card, the first-run Setup
 * step, and the first-run Picker step so the same logic decides
 * what gets shown after "Hello, " across the whole onboarding.
 */
export function firstNameOf(fullName: string | null | undefined): string | null {
  if (!fullName) return null
  const trimmed = fullName.trim()
  if (!trimmed) return null
  const first = trimmed.split(/\s+/)[0]
  return first || null
}
