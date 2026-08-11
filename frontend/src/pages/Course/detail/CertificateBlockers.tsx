import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { AlertCircle } from "lucide-react"
import type { CertificateBlocker, Module } from "@/types"

/**
 * Why the certificate is not available yet — in specifics, with links.
 *
 * The gate that will enforce this ships at the end of the phase; the
 * explanation ships first on purpose. A refusal a student cannot act on turns
 * into a message to the teacher, and a teacher who gets that message five
 * times a week starts approving certificates to make it stop.
 *
 * The backend sends codes and numbers, never sentences. The words are here, in
 * whatever language the reader has chosen — a reason list assembled server-side
 * would need reassembling for every language added, and would drift between
 * this card and the teacher's.
 */
/**
 * Codes this build has words for. Anything else falls back to a sentence that
 * still tells the student what to do — the backend enforces the gate, so a
 * frontend that renders a raw key (or nothing) next to a blocked certificate
 * leaves a refusal with no explanation, which is the failure this card exists
 * to prevent.
 */
const KNOWN_CODES = new Set([
  "course_not_complete",
  "work_not_graded",
  "work_returned",
  "work_not_submitted",
  "quizzes_not_passed",
  "below_threshold",
  "not_assessed",
])

export function CertificateBlockers({
  blockers,
  modules,
  courseId,
}: {
  blockers: CertificateBlocker[]
  modules: Module[]
  courseId: string
}) {
  const { t } = useTranslation()
  if (blockers.length === 0) return null

  // Chapter → its module, so a link can be built. The API deliberately answers
  // "which chapter", not "which URL": routes are the frontend's business.
  const chapterLookup = new Map<string, { moduleId: string; title: string }>()
  for (const module of modules) {
    for (const chapter of module.chapters ?? []) {
      chapterLookup.set(chapter.id, { moduleId: module.id, title: chapter.title })
    }
  }

  return (
    <div className="rounded-lg border border-warning/40 bg-warning/5 px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-sm font-medium">
        <AlertCircle className="h-4 w-4 shrink-0 text-warning" strokeWidth={1.75} aria-hidden />
        {t("myGrade.certificate.notYetTitle")}
      </p>
      <ul className="mt-1.5 space-y-1 text-sm text-ink-muted">
        {blockers.map((blocker) => {
          // A chapter the student cannot see (deleted since, or not in the
          // structure this page loaded) drops out rather than rendering a dead
          // link — the sentence still stands on its own.
          const chapters = blocker.chapter_ids.filter((id) => chapterLookup.has(id))
          return (
            <li key={blocker.code}>
              {t(
                KNOWN_CODES.has(blocker.code)
                  ? `myGrade.certificate.reason.${blocker.code}`
                  : "myGrade.certificate.reason.unknown",
                {
                  ...blocker.params,
                  // Итоговая counts unmarked work as zero, so while anything
                  // is unread the figure is a floor that can only rise. Saying
                  // so is the difference between "you are failing" and "not all
                  // of it has been read yet".
                  context: blocker.params.provisional ? "provisional" : undefined,
                },
              )}
              {chapters.length > 0 && (
                <span className="ml-1">
                  {chapters.map((chapterId, index) => (
                    <span key={chapterId}>
                      {index > 0 && ", "}
                      <Link
                        className="underline underline-offset-2 hover:text-ink"
                        to={`/courses/${courseId}/modules/${chapterLookup.get(chapterId)!.moduleId}/chapters/${chapterId}`}
                      >
                        {chapterLookup.get(chapterId)!.title}
                      </Link>
                    </span>
                  ))}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
