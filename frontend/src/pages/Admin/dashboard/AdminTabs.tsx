import { useTranslation } from "react-i18next"
import { Users, GraduationCap, FileText } from "lucide-react"
import { cn } from "@/lib/utils"
import type { AdminTab } from "./constants"

interface Props {
  active: AdminTab
  onChange: (next: AdminTab) => void
}

/**
 * Underlined tab bar at the top of the Admin Dashboard.
 *
 * Hover gets a subtle muted-foreground bump (was just color-shift),
 * and the active-tab underline picks up a tiny ``shadow`` so the bar
 * reads as a real tab strip continuous with the card below rather
 * than three independently coloured buttons.
 */
export function AdminTabs({ active, onChange }: Props) {
  const { t } = useTranslation()
  return (
    <div className="mb-6 flex gap-1 border-b border-border sm:mb-8" role="tablist">
      <TabButton
        active={active === "overview"}
        onClick={() => onChange("overview")}
        icon={<Users className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
        label={t("admin.tabOverview")}
      />
      <TabButton
        active={active === "cohorts"}
        onClick={() => onChange("cohorts")}
        icon={<GraduationCap className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
        label={t("admin.tabCohorts")}
      />
      <TabButton
        active={active === "audit"}
        onClick={() => onChange("audit")}
        icon={<FileText className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
        label={t("admin.tabAudit")}
      />
    </div>
  )
}

interface TabButtonProps {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}

function TabButton({ active, onClick, icon, label }: TabButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "relative min-h-[44px] px-3 py-2.5 text-sm font-medium transition-colors sm:min-h-0 sm:px-4",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 rounded-t-sm",
        active
          ? "text-primary"
          : "text-muted-foreground hover:bg-muted/40 hover:text-foreground",
      )}
    >
      <div className="flex items-center gap-2">
        {icon}
        {label}
      </div>
      {active && (
        // ``-mb-px`` pulls the underline down by 1px so it sits on top
        // of the ``border-b`` of the parent strip — without it, the
        // underline floats one pixel above the border and the active
        // tab reads as detached from the content card below.
        <div className="absolute -bottom-px left-0 right-0 h-0.5 rounded-t bg-primary" />
      )}
    </button>
  )
}
