import type { NoteInList } from "@/services/notes"

interface CourseGroup {
  courseId: string
  courseTitle: string | null
  modules: { moduleId: string | null; moduleTitle: string | null; notes: NoteInList[] }[]
}

/** The server sends notes in course order; this only groups them. */
export function groupNotes(notes: NoteInList[]): CourseGroup[] {
  const courses: CourseGroup[] = []
  for (const note of notes) {
    let course = courses.find((c) => c.courseId === note.course_id)
    if (!course) {
      course = { courseId: note.course_id, courseTitle: note.course_title, modules: [] }
      courses.push(course)
    }
    let mod = course.modules.find((m) => m.moduleId === note.module_id)
    if (!mod) {
      mod = { moduleId: note.module_id, moduleTitle: note.module_title, notes: [] }
      course.modules.push(mod)
    }
    mod.notes.push(note)
  }
  return courses
}
