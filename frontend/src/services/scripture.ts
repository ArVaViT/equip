import api, { currentAcceptLanguage } from "./api"

export interface Passage {
  /** The reference exactly as the lesson writes it, e.g. «Деян. 1:8». */
  written: string
  ref: string
  text: string
  /** bsb, kjv, nrt, elberfelder, kulish — named by `scripture.edition.*`. */
  edition: string
}

// One answer per block text and language for the life of the page: going
// back and forth between lessons asks nothing twice.
const cache = new Map<string, Promise<Passage[]>>()

/** A reference has a chapter and a verse: `1:8`, or the German `8,28`. */
const MIGHT_CITE = /\d[:,]\s?\d/

// Every block of a lesson asks in the same tick; they go as one request.
let queue: { text: string; key: string; resolve: (p: Passage[]) => void }[] = []

/** The server's limits per request (`app/api/v1/scripture.py`), with room to spare. */
const MAX_TEXTS = 80
const MAX_CHARS = 50_000

type Pending = (typeof queue)[number]

function send(batch: Pending[]) {
  api
    .post<Passage[][]>("/scripture/passages", { texts: batch.map((b) => b.text) })
    .then((r) => batch.forEach((b, i) => b.resolve(r.data[i] ?? [])))
    .catch(() =>
      batch.forEach((b) => {
        // A failure is not remembered: the next visit asks again.
        cache.delete(b.key)
        b.resolve([])
      }),
    )
}

function flush() {
  const all = queue
  queue = []
  // A long lesson goes in as many requests as the limits need — one over
  // them was refused whole, and every reference in the lesson went unlinked.
  let batch: Pending[] = []
  let chars = 0
  for (const p of all) {
    if (p.text.length > MAX_CHARS) {
      // A single block longer than a request may carry: left unlinked.
      p.resolve([])
      continue
    }
    if (batch.length === MAX_TEXTS || chars + p.text.length > MAX_CHARS) {
      send(batch)
      batch = []
      chars = 0
    }
    batch.push(p)
    chars += p.text.length
  }
  if (batch.length > 0) send(batch)
}

export const scriptureService = {
  /**
   * The verses `text` cites that can be shown in the reader's language.
   * Text without a chapter-and-verse pattern is not sent at all, and a
   * failure is an empty list: the lesson reads the same, only unlinked.
   */
  passagesIn(text: string): Promise<Passage[]> {
    if (!MIGHT_CITE.test(text)) return Promise.resolve([])
    const key = `${currentAcceptLanguage()}\n${text}`
    let pending = cache.get(key)
    if (!pending) {
      pending = new Promise<Passage[]>((resolve) => {
        if (queue.length === 0) setTimeout(flush, 0)
        queue.push({ text, key, resolve })
      })
      cache.set(key, pending)
    }
    return pending
  },
}
