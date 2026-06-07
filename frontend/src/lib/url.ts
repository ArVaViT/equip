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
