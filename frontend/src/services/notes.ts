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
}

/** Mirrors ``NOTE_MAX_LENGTH`` in ``app/api/v1/notes.py``. */
export const NOTE_MAX_LENGTH = 10_000

/** A student's own notes on lessons. Never cached: they are being typed. */
export const notesService = {
  async get(chapterId: string): Promise<LessonNote> {
    return (await api.get<LessonNote>(`/notes/chapters/${encodeURIComponent(chapterId)}`)).data
  },
  /** An empty body deletes the note. */
  async save(chapterId: string, body: string): Promise<LessonNote> {
    return (await api.put<LessonNote>(`/notes/chapters/${encodeURIComponent(chapterId)}`, { body })).data
  },
  async mine(): Promise<NoteInList[]> {
    return (await api.get<NoteInList[]>("/notes/me")).data
  },
}
