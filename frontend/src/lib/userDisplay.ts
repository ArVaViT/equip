/**
 * Whitespace-safe display name. ``full_name`` that's null, empty, or
 * whitespace-only falls back to ``email``. Used everywhere the admin
 * surface needs a non-blank label for a user.
 *
 * The naive ``full_name || email`` pattern fails for whitespace-only
 * names (``"   "`` is truthy in JS), so the row would render three
 * blank glyphs as the "name". Extracted here so every callsite gets
 * the same correctness without re-implementing the trim.
 */
export function displayNameOf(
  fullName: string | null | undefined,
  email: string,
): string {
  const trimmed = fullName?.trim()
  return trimmed || email
}
