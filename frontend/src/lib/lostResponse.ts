import { isAxiosError } from "axios"

/**
 * A request whose answer never arrived may still have reached the server.
 *
 * A quiz attempt or an assignment submission is a POST, and the server does
 * not know the second press from the first: when the connection dropped
 * after the request went out, the student saw «could not submit», pressed
 * again, and spent a second attempt — or handed the essay in twice. Before
 * saying so, the screen asks the server what it holds; a new row since the
 * press means the first one landed.
 *
 * Only «no answer at all» qualifies. A 4xx or 5xx is an answer, and the
 * server did not keep what it refused.
 */
export function answerWasLost(err: unknown): boolean {
  return isAxiosError(err) && !err.response
}

/**
 * The newest of `rows` the screen had not seen before the press, or `null`.
 * `known` are the ids on screen when the request went out; a row outside
 * that set is the request's own — unless it is older than `after`, the
 * server's own stamp on the newest row the screen held. A screen that keeps
 * only the latest submission has not «seen» the ones before it, and
 * without the stamp an earlier, already-marked copy in the history passed
 * for the one just sent. Server times are compared with server times only;
 * the client's clock plays no part.
 */
export function newestUnseen<T extends { id: string }>(
  rows: T[],
  known: ReadonlySet<string>,
  when: (row: T) => string | null | undefined,
  after?: string | null,
): T | null {
  const floor = after ? Date.parse(after) : Number.NEGATIVE_INFINITY
  let found: T | null = null
  for (const row of rows) {
    if (known.has(row.id)) continue
    const at = Date.parse(when(row) ?? "")
    // A row without a readable stamp cannot be placed after the floor.
    if (Number.isFinite(floor) && !(at > floor)) continue
    if (!found || at > Date.parse(when(found) ?? "")) found = row
  }
  return found
}
