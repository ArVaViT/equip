import api from "./api"

export interface LessonNote {
  chapter_id: string
  body: string | null
  updated_at: string | null
}

export interface NoteInList {
  chapter_id: string
  chapter_title: string | null
  module_id: string | null
  module_title: string | null
  course_id: string
  course_title: string | null
  body: string
  updated_at: string
  /** Whether the lesson can still be opened (published, still enrolled). */
  available: boolean
}

/** Mirrors ``NOTE_MAX_LENGTH`` in ``app/api/v1/notes.py``. */
export const NOTE_MAX_LENGTH = 10_000

// Saves per lesson, across component instances: leaving a lesson sends its
// last save, and coming straight back must not read the note before that
// save lands — the older text would come back and the next save would
// overwrite the one that was still in flight.
const pending = new Map<string, Promise<unknown>>()

/** Every save still in flight, each allowed to fail. */
function settled(): Promise<unknown> {
  return Promise.allSettled([...pending.values()])
}

/** A student's own notes on lessons. Never cached: they are being typed. */
export const notesService = {
  async get(chapterId: string): Promise<LessonNote> {
    await pending.get(chapterId)?.catch(() => undefined)
    return (await api.get<LessonNote>(`/notes/chapters/${encodeURIComponent(chapterId)}`)).data
  },
  /** An empty body deletes the note. Saves of one lesson run one after another. */
  save(chapterId: string, body: string): Promise<LessonNote> {
    const previous = pending.get(chapterId) ?? Promise.resolve()
    const next = previous
      .catch(() => undefined)
      .then(async () => (await api.put<LessonNote>(`/notes/chapters/${encodeURIComponent(chapterId)}`, { body })).data)
    pending.set(chapterId, next)
    void next
      .catch(() => undefined)
      .finally(() => {
        if (pending.get(chapterId) === next) pending.delete(chapterId)
      })
    return next
  },
  async remove(chapterId: string): Promise<void> {
    await settled()
    await api.delete(`/notes/chapters/${encodeURIComponent(chapterId)}`)
  },
  /** Every note, after any save still on its way — "All notes" from a lesson
   *  must list what was just typed there. */
  async mine(): Promise<NoteInList[]> {
    await settled()
    return (await api.get<NoteInList[]>("/notes/me")).data
  },
}
