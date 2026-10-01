import { useContext, useState } from "react"
import { useTranslation } from "react-i18next"
import { BookmarkPlus, Library, X } from "lucide-react"

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { AuthContext } from "@/context/auth-context"
import { toast } from "@/lib/toast"
import { COMMENT_MAX_LENGTH, usersService } from "@/services/users"

/**
 * The teacher's saved comments, beside a feedback box.
 *
 * Marking forty essays, a teacher writes the same few remarks thirty times.
 * Saved once, each goes into the feedback in one click — added to what is
 * already written, never replacing it — and the quality of feedback stops
 * depending on how late in the pile an essay came. Kept on the teacher's
 * profile, so the library follows them between devices.
 */
export function CommentLibrary({ current, onInsert }: { current: string; onInsert: (text: string) => void }) {
  const { t } = useTranslation()
  // Read without requiring a provider: outside a signed-in page (and in the
  // graders' own tests) there is no library to show, and no reason to fail.
  const auth = useContext(AuthContext)
  const [busy, setBusy] = useState(false)
  const user = auth?.user
  const applyUser = auth?.applyUser
  if (!user || !applyUser) return null
  const library = user.comment_library ?? []
  const draft = current.trim().slice(0, COMMENT_MAX_LENGTH)

  const edit = async (change: { add?: string; remove?: string }) => {
    setBusy(true)
    try {
      const saved = await usersService.editCommentLibrary(change)
      applyUser({ id: user.id, comment_library: saved })
    } catch {
      toast({ title: t("profile.updateFailed"), variant: "destructive" })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Popover>
      <PopoverTrigger className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-ink-muted transition-colors hover:bg-muted/40 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand">
        <Library className="h-3 w-3" strokeWidth={1.75} aria-hidden />
        {t("grading.library.open", { count: library.length })}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-2 p-3">
        {library.length === 0 ? (
          <p className="text-xs text-ink-muted">{t("grading.library.empty")}</p>
        ) : (
          <ul className="max-h-64 space-y-1 overflow-y-auto">
            {library.map((comment) => (
              <li key={comment} className="flex items-start gap-1">
                <button
                  type="button"
                  onClick={() => onInsert(comment)}
                  className="min-w-0 flex-1 rounded px-2 py-1 text-left text-xs transition-colors hover:bg-muted/40"
                >
                  {comment}
                </button>
                <button
                  type="button"
                  aria-label={t("grading.library.remove", { comment })}
                  disabled={busy}
                  onClick={() => void edit({ remove: comment })}
                  className="shrink-0 rounded p-1 text-ink-muted opacity-60 transition-opacity hover:opacity-100"
                >
                  <X className="h-3 w-3" strokeWidth={1.75} aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          disabled={busy || draft === "" || library.includes(draft)}
          onClick={() => void edit({ add: draft })}
          className="inline-flex w-full items-center justify-center gap-1.5 rounded-md border border-edge px-2 py-1.5 text-xs transition-colors hover:bg-muted/40 disabled:opacity-50"
        >
          <BookmarkPlus className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          {t("grading.library.save")}
        </button>
      </PopoverContent>
    </Popover>
  )
}

