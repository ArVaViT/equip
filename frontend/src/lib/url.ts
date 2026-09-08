/**
 * True only for fully-qualified http(s) URLs. Used to gate user-supplied
 * URLs before they land in an `<a href>` — React does NOT block dangerous
 * schemes like `javascript:` in href, so a stored `javascript:…` value would
 * execute in the viewer's session on click.
 *
 * Defence-in-depth: the backend already rejects non-`https://` submission
 * URLs (`schemas/assignment.py::_enforce_https_scheme`); this keeps the
 * render side safe even if an upstream check ever regresses.
 */
export function isHttpUrl(url: string | null | undefined): boolean {
  if (!url) return false
  try {
    const parsed = new URL(url, window.location.origin)
    return parsed.protocol === "http:" || parsed.protocol === "https:"
  } catch {
    return false
  }
}

/**
 * The same question for a link the user typed rather than one the app
 * built: is this a whole web address, on its own, that we would be
 * willing to send someone to?
 *
 * `isHttpUrl` resolves against the current origin, so it answers true
 * for `/courses/1` and for `zoom.us/j/1` — correct for its job (gating
 * an `href` we are about to render) and wrong for this one. A teacher
 * typing where her class meets cannot mean a path on Equip, and
 * `zoom.us/j/1` without a scheme is a link that will not open. Both are
 * refused here so the form can say so while she is still looking at the
 * field.
 *
 * Userinfo is refused too: `https://zoom.us@evil.com` is a link to
 * `evil.com` wearing `zoom.us` as a costume. This mirrors
 * `normalize_meeting_url` on the server — the server is the authority,
 * and this exists so the answer arrives without a round trip.
 */
export function isAbsoluteHttpUrl(url: string | null | undefined): boolean {
  if (!url) return false
  try {
    // No base argument: a relative value throws here rather than being
    // silently resolved into an absolute one.
    const parsed = new URL(url)
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return false
    if (parsed.username || parsed.password) return false
    return Boolean(parsed.hostname)
  } catch {
    return false
  }
}
