/**
 * Where an invitation token lives in the accept page's URL.
 *
 * Letters sent from 2026-09-16 carry it in the fragment,
 * `/invite/accept#token=…`. A browser never sends a fragment to a server,
 * so it stays out of the frontend host's edge log — which, for the
 * `?token=` letters before it, recorded every visit with the token in
 * full — and out of the `Referer` of every request the page makes.
 *
 * Letters already delivered still say `?token=`, and they keep working
 * for the rest of their seven days: the query is read when the fragment
 * has nothing.
 */

type UrlParts = { search: string; hash: string }

function tokenIn(part: string): string {
  return new URLSearchParams(part.replace(/^[?#]/, "")).get("token") ?? ""
}

export function inviteTokenFrom(location: UrlParts): string {
  return tokenIn(location.hash) || tokenIn(location.search)
}

/** True when the token came from the query, i.e. from an older letter. */
export function inviteTokenIsInQuery(location: UrlParts): boolean {
  return !tokenIn(location.hash) && tokenIn(location.search) !== ""
}

/** The accept page for `token`, with the token where no server sees it. */
export function inviteAcceptPath(token: string): { pathname: string; search: string; hash: string } {
  return { pathname: "/invite/accept", search: "", hash: `token=${encodeURIComponent(token)}` }
}
