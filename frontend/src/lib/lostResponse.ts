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
 * that set is the request's own.
 */
export function newestUnseen<T extends { id: string }>(
  rows: T[],
  known: ReadonlySet<string>,
  when: (row: T) => string | null | undefined,
): T | null {
  let found: T | null = null
  for (const row of rows) {
    if (known.has(row.id)) continue
    if (!found || Date.parse(when(row) ?? "") > Date.parse(when(found) ?? "")) found = row
  }
  return found
}
