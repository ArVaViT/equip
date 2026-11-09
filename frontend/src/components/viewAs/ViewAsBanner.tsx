import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Eye } from "lucide-react"
import { Button } from "@/components/ui/button"
import { activeViewAs, clearViewAs } from "@/lib/viewAs"
import { viewAsService } from "@/services/viewAs"

/**
 * On every page while a platform admin views as someone else: whose eyes,
 * that nothing can be changed, until when, and the way back.
 */
export function ViewAsBanner() {
  const { t } = useTranslation()
  const [leaving, setLeaving] = useState(false)
  const view = activeViewAs()
  if (!view) return null

  const until = new Date(view.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  const who = view.person.full_name ? `${view.person.full_name} (${view.person.email})` : view.person.email

  const leave = async () => {
    setLeaving(true)
    try {
      await viewAsService.end(view.id)
    } catch {
      // Ending is a courtesy to the audit log; the view lapses on its own.
    }
    clearViewAs()
    window.location.assign("/admin")
  }

  return (
    <div role="status" className="sticky top-0 z-50 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-warning bg-warning px-4 py-2 text-sm font-medium text-warning-foreground">
      <Eye className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
      <span>{t("viewAs.banner", { who, until })}</span>
      <Button size="sm" variant="outline" onClick={leave} disabled={leaving} className="h-7">
        {t("viewAs.leave")}
      </Button>
    </div>
  )
}
