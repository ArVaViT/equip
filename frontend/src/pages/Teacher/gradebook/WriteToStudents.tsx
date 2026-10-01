import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { Copy, Mail } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { toast } from "@/lib/toast"
import { orNotTranslated } from "@/lib/untranslated"
import { isWork, MAILTO_MAX, mailtoFor, pickRecipients, type Audience } from "./recipients"
import type { StudentProgressData } from "./types"

const AUDIENCES: Audience[] = ["not_submitted", "not_passed", "everyone"]

/**
 * "Write to those who…": the volunteer's Monday-morning act, from the
 * gradebook. Pick a piece of work and who — not handed in, not passed, or
 * the whole class — see the names, and open a note in one's own mail with
 * them in Bcc, or copy the addresses. Equip sends nothing itself.
 */
export function WriteToStudents({ courseTitle, students }: { courseTitle: string; students: StudentProgressData[] }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const works = useMemo(() => (students[0]?.chapters ?? []).filter(isWork), [students])
  const [chapterId, setChapterId] = useState<string | null>(null)
  const [audience, setAudience] = useState<Audience>("not_submitted")
  const selected = chapterId ?? works[0]?.id ?? null
  const work = works.find((w) => w.id === selected)
  const recipients = pickRecipients(students, selected, audience)
  const emails = recipients.map((s) => s.email)
  const subject = work && audience !== "everyone" ? `${courseTitle}: ${orNotTranslated(t, work.title)}` : courseTitle
  const mailto = mailtoFor(emails, subject)
  const tooLong = mailto.length > MAILTO_MAX

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(emails.join(", "))
      toast({ title: t("gradebook.write.copied", { count: emails.length }) })
    } catch {
      toast({ title: t("gradebook.write.copyFailed"), variant: "destructive" })
    }
  }

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Mail className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
        {t("gradebook.write.open")}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("gradebook.write.title")}</DialogTitle>
          </DialogHeader>
          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-sm font-medium">{t("gradebook.write.who")}</legend>
            {AUDIENCES.map((a) => (
              <label key={a} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="audience"
                  value={a}
                  checked={audience === a}
                  onChange={() => setAudience(a)}
                  disabled={a !== "everyone" && works.length === 0}
                />
                {t(`gradebook.write.audience.${a}`)}
              </label>
            ))}
          </fieldset>
          {audience !== "everyone" && works.length > 0 && (
            <label className="block space-y-1 text-sm">
              <span className="font-medium">{t("gradebook.write.work")}</span>
              <select
                value={selected ?? ""}
                onChange={(e) => setChapterId(e.target.value)}
                className="w-full rounded-md border border-edge bg-surface px-2 py-1.5 text-sm"
              >
                {works.map((w) => (
                  <option key={w.id} value={w.id}>
                    {orNotTranslated(t, w.title)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="space-y-1" aria-live="polite">
            <p className="text-sm">{t("gradebook.write.count", { count: recipients.length })}</p>
            {recipients.length > 0 && (
              <p className="max-h-32 overflow-y-auto text-xs text-ink-muted">
                {recipients.map((s) => s.full_name || s.email).join(", ")}
              </p>
            )}
          </div>
          {tooLong && <p className="text-xs text-ink-muted">{t("gradebook.write.tooMany")}</p>}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" size="sm" onClick={() => void copy()} disabled={emails.length === 0}>
              <Copy className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
              {t("gradebook.write.copy")}
            </Button>
            {emails.length > 0 && !tooLong ? (
              <Button asChild size="sm">
                <a href={mailto}>
                  <Mail className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                  {t("gradebook.write.compose")}
                </a>
              </Button>
            ) : (
              <Button size="sm" disabled>
                <Mail className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                {t("gradebook.write.compose")}
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
