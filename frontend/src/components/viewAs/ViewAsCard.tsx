import { useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"
import { Eye } from "lucide-react"
import { Button } from "@/components/ui/button"
import { setViewAs } from "@/lib/viewAs"
import { viewAsService } from "@/services/viewAs"
import { isAxiosError } from "axios"

/** Admin overview: open Equip as another person, read-only, for 30 minutes. */
export function ViewAsCard() {
  const { t } = useTranslation()
  const [email, setEmail] = useState("")
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const view = await viewAsService.start(email.trim(), reason.trim())
      setViewAs(view)
      window.location.assign("/")
    } catch (err) {
      setError(isAxiosError(err) && err.response?.status === 404 ? t("viewAs.notFound") : t("viewAs.failed"))
      setBusy(false)
    }
  }

  return (
    <section className="mb-8 rounded-lg border border-edge bg-surface p-4">
      <div className="mb-1 flex items-center gap-2">
        <Eye className="h-4 w-4 text-ink-muted" strokeWidth={1.75} aria-hidden />
        <h2 className="text-base font-semibold">{t("viewAs.title")}</h2>
      </div>
      <p className="mb-3 text-sm text-ink-muted">{t("viewAs.hint")}</p>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t("viewAs.emailPlaceholder")}
          aria-label={t("viewAs.emailPlaceholder")}
          className="h-9 flex-1 rounded-md border border-edge bg-transparent px-3 text-sm"
        />
        <input
          required
          minLength={3}
          maxLength={500}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t("viewAs.reasonPlaceholder")}
          aria-label={t("viewAs.reasonPlaceholder")}
          className="h-9 flex-1 rounded-md border border-edge bg-transparent px-3 text-sm"
        />
        <Button type="submit" size="sm" disabled={busy} className="h-9">
          {t("viewAs.start")}
        </Button>
      </form>
      {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
    </section>
  )
}
