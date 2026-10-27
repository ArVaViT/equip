import { useTranslation } from "react-i18next"
import { Wifi, WifiOff } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { useOnlineStatus } from "@/hooks/useOnlineStatus"

export function ConnectionStatus() {
  const { t } = useTranslation()
  const online = useOnlineStatus()
  const Icon = online ? Wifi : WifiOff

  return (
    <Badge
      variant={online ? "successSubtle" : "warningSubtle"}
      className="shrink-0 gap-1.5"
      role="status"
      aria-live="polite"
    >
      <Icon className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
      {online ? t("offline.online") : t("offline.offline")}
    </Badge>
  )
}
