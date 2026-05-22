import { useTranslation } from "react-i18next"
import { TrendingUp, LayoutGrid } from "lucide-react"
import type { ActiveTab } from "./types"

interface Props {
  active: ActiveTab
  onChange: (tab: ActiveTab) => void
}

/** Two-button tab switcher for "Summary Grades" vs "Grade Table". */
export function GradebookTabs({ active, onChange }: Props) {
  const { t } = useTranslation()
  return (
    <div className="flex gap-1 mb-6 border-b">
      <TabButton
        active={active === "summary"}
        onClick={() => onChange("summary")}
        icon={<TrendingUp className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
        label={t("gradebook.summaryTab")}
      />
      <TabButton
        active={active === "table"}
        onClick={() => onChange("table")}
        icon={<LayoutGrid className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
        label={t("gradebook.tableTab")}
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
      className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
        active
          ? "border-primary text-primary"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
    >
      {icon}
      {label}
    </button>
  )
}
