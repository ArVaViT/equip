import { useEffect, useId, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAuth } from "@/context/useAuth"
import { usersService } from "@/services/users"
import { toast } from "@/lib/toast"

interface Props {
  /** Fires when the step is over — the name saved, the save failed, or the
   *  person chose to skip. The gate must move on in every case; the
   *  profile page is where a failed save gets retried. */
  onDone: () => void
}

/**
 * First-run — the name, asked only when the profile has none.
 *
 * This replaced a 431-line "Quick setup" screen that asked for a photo, a
 * display name, a theme and a language, and showed the email read-only with
 * a hint about where to change it. Every one of those has a home already:
 * the photo and the name on the profile page, the theme and the language in
 * the header of every page. Asking them before the person has seen a single
 * course was a wall of choices in front of the thing they came for, and each
 * one came with its own failure and rollback path.
 *
 * What survives is the one field that usually has no answer yet: a Google
 * sign-up carries a name, and an email sign-up types one, but a profile can
 * still be nameless — an invitation, an older account, a form left blank —
 * and a nameless student is a problem for the teacher reading the roster
 * and for the certificate that prints it. So the question is asked once,
 * only when it applies, and can be skipped.
 */
export function NameStep({ onDone }: Props) {
  const { t } = useTranslation()
  const { refreshUser } = useAuth()
  const inputRef = useRef<HTMLInputElement>(null)
  const inputId = useId()
  const [name, setName] = useState("")
  const [saving, setSaving] = useState(false)

  // Land the cursor in the field so the screen reads as a question, not a
  // form to inspect. ``requestAnimationFrame`` waits for the commit so the
  // focus call does not lose to the dialog's own first-focusable logic.
  useEffect(() => {
    const id = window.requestAnimationFrame(() => inputRef.current?.focus())
    return () => window.cancelAnimationFrame(id)
  }, [])

  const trimmed = name.trim()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!trimmed) return
    setSaving(true)
    try {
      await usersService.updateProfile({ full_name: trimmed })
    } catch {
      toast({ title: t("firstRun.name.saveFailed"), variant: "destructive" })
    }
    try {
      await refreshUser()
    } catch {
      /* the cached profile catches up on the next load */
    }
    setSaving(false)
    onDone()
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex w-full max-w-md flex-col items-center gap-5 text-center"
    >
      <span className="block h-px w-12 bg-accent/60" aria-hidden />
      <p className="text-xs font-medium uppercase tracking-[0.22em] text-accent">
        {t("firstRun.name.eyebrow")}
      </p>
      <h1 className="font-serif text-2xl font-semibold leading-tight tracking-tight text-ink sm:text-3xl">
        {t("firstRun.name.title")}
      </h1>

      <div className="mt-2 w-full text-left">
        <Label
          htmlFor={inputId}
          className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted"
        >
          {t("firstRun.name.label")}
        </Label>
        <Input
          ref={inputRef}
          id={inputId}
          value={name}
          onChange={(e) => setName(e.target.value.slice(0, 100))}
          placeholder={t("firstRun.name.placeholder")}
          maxLength={100}
          autoComplete="name"
          aria-describedby={`${inputId}-hint`}
          className="mt-2"
        />
        <p id={`${inputId}-hint`} className="mt-1.5 text-xs text-ink-muted">
          {t("firstRun.name.hint")}
        </p>
      </div>

      <div className="mt-2 flex w-full flex-col items-center gap-2 sm:flex-row sm:justify-center">
        <Button
          type="submit"
          disabled={!trimmed || saving}
          size="lg"
          className="w-full sm:w-auto sm:min-w-[160px]"
        >
          {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />}
          {t("firstRun.name.submit")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onDone}
          disabled={saving}
          className="text-ink-muted hover:text-ink"
        >
          {t("firstRun.name.skip")}
        </Button>
      </div>
    </form>
  )
}
