import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Link } from "react-router-dom"
import { NotebookPen, RefreshCw, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useConfirm } from "@/components/ui/alert-dialog"
import PageSpinner from "@/components/ui/PageSpinner"
import { Section } from "@/components/layout/Section"
import { EmptyState, ErrorState, PageHeader } from "@/components/patterns"
import { useAsyncData } from "@/hooks/useAsyncData"
import { formatDateLong } from "@/i18n/format"
import { chapterHref } from "@/lib/courseStructure"
import { toast } from "@/lib/toast"
import { orNotTranslated } from "@/lib/untranslated"
import { notesService } from "@/services/notes"
import { groupNotes } from "./groupNotes"

/**
 * Every note a student has written on a lesson, by course and module — the
 * margins of their Bible gathered in one place, each a link back to the
 * lesson it was written beside.
 */
export default function MyNotesPage() {
  const { t } = useTranslation()
  const { data, loading, error, refetch } = useAsyncData(() => notesService.mine(), [])
  const [removed, setRemoved] = useState<Set<string>>(new Set())
  const confirm = useConfirm()
  const remove = async (chapterId: string) => {
    const ok = await confirm({
      title: t("notes.page.deleteConfirmTitle"),
      description: t("notes.page.deleteConfirmDescription"),
      confirmLabel: t("notes.page.delete"),
      tone: "destructive",
    })
    if (!ok) return
    try {
      await notesService.remove(chapterId)
      setRemoved((prev) => new Set(prev).add(chapterId))
    } catch {
      toast({ title: t("notes.page.deleteFailed"), variant: "destructive" })
    }
  }
  const notes = (data ?? []).filter((n) => !removed.has(n.chapter_id))

  if (loading) return <PageSpinner />

  return (
    <Section>
      <PageHeader eyebrow={t("notes.page.eyebrow")} title={t("notes.page.title")} />
      {error ? (
        <ErrorState
          description={t("notes.page.loadFailed")}
          action={
            <Button size="sm" onClick={refetch}>
              <RefreshCw className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
              {t("common.tryAgain")}
            </Button>
          }
        />
      ) : notes.length === 0 ? (
        <EmptyState
          icon={<NotebookPen strokeWidth={1.75} aria-hidden />}
          title={t("notes.page.emptyTitle")}
          description={t("notes.page.emptyDescription")}
        />
      ) : (
        <div className="space-y-10">
          {groupNotes(notes).map((course) => (
            <section key={course.courseId} aria-labelledby={`notes-${course.courseId}`}>
              <h2 id={`notes-${course.courseId}`} className="mb-4 font-serif text-xl font-semibold">
                {course.courseTitle ??
                  (course.modules.every((m) => m.notes.every((n) => !n.available))
                    ? t("notes.page.courseUnavailable")
                    : orNotTranslated(t, ""))}
              </h2>
              <div className="space-y-6">
                {course.modules.map((mod) => (
                  <div key={mod.moduleId ?? "loose"}>
                    {mod.moduleId && mod.notes.some((n) => n.available) && (
                      <h3 className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-ink-muted">
                        {orNotTranslated(t, mod.moduleTitle ?? "")}
                      </h3>
                    )}
                    <ul className="space-y-3">
                      {mod.notes.map((note) => (
                        <li key={note.chapter_id} className="rounded-md border border-edge p-4">
                          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                            {note.available ? (
                              <Link
                                to={chapterHref(note.course_id, note.chapter_id)}
                                className="text-sm font-medium underline-offset-4 hover:underline"
                              >
                                {orNotTranslated(t, note.chapter_title ?? "")}
                              </Link>
                            ) : (
                              // A course since unpublished or left: the words
                              // stay, the link that would 404 does not.
                              <span className="text-sm font-medium text-ink-muted">{t("notes.page.unavailable")}</span>
                            )}
                            <span className="flex items-center gap-2">
                              <time dateTime={note.updated_at} className="text-xs text-ink-muted">
                                {formatDateLong(note.updated_at)}
                              </time>
                              <button
                                type="button"
                                onClick={() => void remove(note.chapter_id)}
                                aria-label={`${t("notes.page.delete")}: ${orNotTranslated(t, note.chapter_title ?? "")}`}
                                className="rounded p-1 text-ink-muted transition-colors hover:text-destructive"
                              >
                                <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                              </button>
                            </span>
                          </div>
                          <p className="whitespace-pre-wrap text-sm leading-relaxed">{note.body}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </Section>
  )
}
