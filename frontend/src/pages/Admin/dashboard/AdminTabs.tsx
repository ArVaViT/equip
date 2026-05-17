import { useTranslation } from "react-i18next"
import { Users, GraduationCap, FileText } from "lucide-react"
import type { AdminTab } from "./constants"

interface Props {
  active: AdminTab
  onChange: (next: AdminTab) => void
}

/** Underlined tab bar used at the top of the Admin dashboard. */
export function AdminTabs({ active, onChange }: Props) {
  const { t } = useTranslation()
  return (
    <div className="mb-6 flex gap-1 border-b sm:mb-8">
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
      onClick={onClick}
      className={`relative min-h-[44px] px-3 py-2.5 text-sm font-medium transition-colors sm:min-h-0 sm:px-4 ${
        active ? "text-primary" : "text-muted-foreground hover:text-foreground"
      }`}
    >
      <div className="flex items-center gap-2">
        {icon}
        {label}
      </div>
      {active && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-t" />
      )}
    </button>
  )
}
