import { useTranslation } from "react-i18next"
import { WifiOff } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"

export function ConnectionStatus() {
  const { t } = useTranslation()
  const online = useOnlineStatus()
  if (online) return null

  return (
    <Badge
      variant="warningSubtle"
      className="shrink-0 gap-1.5"
      role="status"
      aria-live="polite"
    >
      <WifiOff className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
      {t("offline.offline")}
    </Badge>
  )
}
