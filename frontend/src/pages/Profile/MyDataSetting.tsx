import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Download, FileJson } from "lucide-react"

import { Button } from "@/components/ui/button"
import { toast } from "@/lib/toast"
import api from "@/services/api"

/**
 * "Download my data": everything Equip keeps about the reader, as one JSON
 * file — their right under GDPR, and the plain answer to "what do you have on
 * me?". Fetched with the session like any request, then handed to the
 * browser as a file; the link is revoked once the download has started.
 */
export function MyDataSetting() {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)

  const download = async () => {
    setBusy(true)
    try {
      const response = await api.get<Blob>("/users/me/export", { responseType: "blob" })
      const disposition = String(response.headers["content-disposition"] ?? "")
      const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "equip-my-data.json"
      const url = URL.createObjectURL(response.data)
      const link = document.createElement("a")
      link.href = url
      link.download = name
      document.body.append(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch {
      toast({ title: t("profile.myData.failed"), variant: "destructive" })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-4">
      <div className="flex min-w-0 items-start gap-3">
        <FileJson className="mt-0.5 h-4 w-4 shrink-0 text-ink-muted" strokeWidth={1.75} aria-hidden />
        <div className="min-w-0">
          <p className="text-sm font-medium">{t("profile.myData.label")}</p>
          <p className="text-xs text-ink-muted">{t("profile.myData.hint")}</p>
        </div>
      </div>
      <Button variant="outline" size="sm" onClick={() => void download()} disabled={busy}>
        <Download className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
        {busy ? t("profile.myData.preparing") : t("profile.myData.download")}
      </Button>
    </div>
  )
}
