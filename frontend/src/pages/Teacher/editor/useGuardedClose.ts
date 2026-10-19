import { useCallback } from "react"
import { useTranslation } from "react-i18next"
import type { useConfirm } from "@/components/ui/alert-dialog"

type Confirm = ReturnType<typeof useConfirm>

/**
 * Closing a dialog that holds a form: ask first when something is typed.
 *
 * Escape and a click beside the announcements or events dialog used to
 * throw the form away without a word (2026-10-19) — a paragraph written for
 * a class, gone because the hand slipped. An empty form closes at once; a
 * touched one asks «Close without saving?», through the same AlertDialog
 * every other confirmation on the platform uses.
 *
 * Returns ``(dirty, reset) => Promise<void>``: the caller says whether its
 * form is worth asking about and how to blank it, and the hook decides.
 */
export function useGuardedClose(confirm: Confirm, close: () => void) {
  const { t } = useTranslation()
  return useCallback(
    async (dirty: boolean, reset: () => void) => {
      if (dirty) {
        const ok = await confirm({
          title: t("courseEditor.closeUnsaved.title"),
          description: t("courseEditor.closeUnsaved.description"),
          confirmLabel: t("courseEditor.closeUnsaved.confirm"),
          tone: "destructive",
        })
        if (!ok) return
      }
      close()
      reset()
    },
    [confirm, close, t],
  )
}
