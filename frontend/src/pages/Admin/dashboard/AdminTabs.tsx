import { useEffect, useRef } from "react"
import { useTranslation } from "react-i18next"
import { Building2, Users, GraduationCap, Mail, FileText, Languages, School, Scale } from "lucide-react"
import { cn } from "@/lib/utils"
import { ADMIN_TAB_PANEL_ID, ADMIN_TAB_TRIGGER_ID, type AdminTab } from "./constants"

interface Props {
  active: AdminTab
  onChange: (next: AdminTab) => void
  /** Which tabs this reader may open — all of them for platform staff,
   *  the school's own for a director (``tabsFor``). */
  tabs: readonly AdminTab[]
}

const TAB_META: Record<AdminTab, { icon: typeof Users; labelKey: string }> = {
  overview: { icon: Users, labelKey: "admin.tabOverview" },
  cohorts: { icon: GraduationCap, labelKey: "admin.tabCohorts" },
  invitations: { icon: Mail, labelKey: "admin.tabInvitations" },
  translations: { icon: Languages, labelKey: "admin.tabTranslations" },
  audit: { icon: FileText, labelKey: "admin.tabAudit" },
  school: { icon: School, labelKey: "admin.tabSchool" },
  dmca: { icon: Scale, labelKey: "admin.tabDmca" },
  organizations: { icon: Building2, labelKey: "admin.tabOrganizations" },
}

/**
 * Underlined tab bar at the top of the Admin Dashboard.
 *
 * Hover gets a subtle muted-foreground bump (was just color-shift),
 * and the active-tab underline picks up a tiny ``shadow`` so the bar
 * reads as a real tab strip continuous with the card below rather
 * than three independently coloured buttons.
 */
export function AdminTabs({ active, onChange, tabs }: Props) {
  const { t } = useTranslation()
  return (
    // Eight tabs do not fit a laptop's width: the row scrolls sideways
    // rather than wrapping a label onto two lines or running off the page.
    <div className="no-scrollbar mb-6 flex gap-1 overflow-x-auto border-b border-edge sm:mb-8" role="tablist">
      {tabs.map((name) => {
        const { icon: Icon, labelKey } = TAB_META[name]
        return (
          <TabButton
            key={name}
            name={name}
            active={active === name}
            onClick={() => onChange(name)}
            icon={<Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
            label={t(labelKey)}
          />
        )
      })}
    </div>
  )
}

interface TabButtonProps {
  name: AdminTab
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  label: string
}

function TabButton({ name, active, onClick, icon, label }: TabButtonProps) {
  const ref = useRef<HTMLButtonElement>(null)
  // A tab opened by link may sit past the row's scrolled edge: bring it in.
  useEffect(() => {
    if (active) ref.current?.scrollIntoView?.({ block: "nearest", inline: "nearest" })
  }, [active])
  return (
    <button
      ref={ref}
      type="button"
      role="tab"
      id={ADMIN_TAB_TRIGGER_ID[name]}
      aria-controls={ADMIN_TAB_PANEL_ID[name]}
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "relative min-h-[44px] shrink-0 whitespace-nowrap px-3 py-2.5 text-sm font-medium transition-colors sm:min-h-0 sm:px-4",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 rounded-t-sm",
        active
          ? "text-brand"
          : "text-ink-muted hover:bg-muted/40 hover:text-ink",
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
        // Inside the row, not under it: a scrolling row clips what hangs below.
        <div className="absolute bottom-0 left-0 right-0 h-0.5 rounded-t bg-brand" />
      )}
    </button>
  )
}
