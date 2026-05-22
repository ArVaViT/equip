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

/**
 * Two-character initials for avatar fallbacks — "Vadym Arnaut" → "VA",
 * "vadimarnaut78@gmail.com" → "VA", "Иван" → "И".
 *
 * Splits on whitespace AND ``@`` so an email handle yields a usable
 * pair (the part before the first ``.`` of the local-part isn't worth
 * the extra branching). Uppercase Unicode-aware so Cyrillic + Latin
 * both look right against ``font-serif``.
 *
 * Returns an empty string for null/blank so the caller can decide
 * between "no initials → render the User icon" and "have initials →
 * render the letters" with a single truthy check.
 */
export function initialsOf(nameOrEmail: string | null | undefined): string {
  if (!nameOrEmail) return ""
  return nameOrEmail
    .split(/[\s@]/)
    .slice(0, 2)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("")
}
