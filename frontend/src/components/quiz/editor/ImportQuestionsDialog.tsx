import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { ClipboardPaste } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { parseQuestionsText, type ImportedQuestion } from "./importText"

/**
 * "Paste questions from text": a test brought in Word becomes drafts in the
 * editor, saved like any other with the editor's own Save. The preview below
 * the box counts what will be added and names, by its first line, every
 * block that is not yet a question and why — nothing is dropped silently.
 */
export function ImportQuestionsDialog({ onImport }: { onImport: (questions: ImportedQuestion[]) => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState("")
  const blocks = useMemo(() => parseQuestionsText(text), [text])
  const good = blocks.flatMap((b) => (b.question ? [b.question] : []))
  const bad = blocks.filter((b) => b.problem)

  const add = () => {
    onImport(good)
    setText("")
    setOpen(false)
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)} className="h-7 text-xs">
        <ClipboardPaste className="mr-1 h-3 w-3" strokeWidth={1.75} aria-hidden />
        {t("quizEditor.import.open")}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t("quizEditor.import.title")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-ink-muted">{t("quizEditor.import.howTo")}</p>
          <pre className="rounded-md bg-muted/40 p-3 text-xs leading-relaxed text-ink-muted">{t("quizEditor.import.example")}</pre>
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label={t("quizEditor.import.title")}
            className="min-h-[200px] font-mono text-xs"
          />
          {/* Always rendered: a live region that appears with its content is
              often not announced the first time. */}
          <div className="space-y-1 text-sm" aria-live="polite">
            {text.trim() !== "" && (
              <>
                <p>{t("quizEditor.import.found", { count: good.length })}</p>
                {/* Which option each question will count as right — the one
                    thing a misread letter would get wrong silently. */}
                {good.length > 0 && (
                  <ol className="max-h-40 list-decimal space-y-0.5 overflow-y-auto pl-5 text-xs text-ink-muted">
                    {good.map((q, i) => (
                      <li key={i}>
                        {q.question_text.split("\n")[0]!.slice(0, 60)} —{" "}
                        <span className="text-success-ink">
                          ✓ {q.options.find((o) => o.is_correct)?.option_text.slice(0, 40)}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
                {bad.length > 0 && (
                  <ul className="space-y-0.5 text-xs text-destructive-ink">
                    {bad.map((b, i) => (
                      <li key={i}>
                        «{b.start.slice(0, 60)}» — {t(`quizEditor.import.problem.${b.problem}`)}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button size="sm" onClick={add} disabled={good.length === 0}>
              {t("quizEditor.import.add", { count: good.length })}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
