/**
 * The page a signed-out visitor was heading for.
 *
 * `Gate` sends a guest on a private route to `/login` with the route it
 * refused in the router state; once the person is signed in, the public gate
 * on `/login` sends them back there instead of to the dashboard. A shared
 * course link opened while logged out used to end on the dashboard, with no
 * word that the person had been going somewhere.
 *
 * Only an internal, absolute path is honoured. Router state is set by our
 * own code, but a value that could ever be influenced from outside must not
 * be able to send a fresh sign-in to another site — hence no `//host` form.
 */
export function returnPathFrom(state: unknown): string | null {
  if (!state || typeof state !== "object") return null
  const from = (state as { from?: unknown }).from
  if (typeof from !== "string") return null
  if (!from.startsWith("/") || from.startsWith("//")) return null
  return from
}
