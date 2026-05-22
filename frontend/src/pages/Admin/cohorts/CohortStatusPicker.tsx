import { useTranslation } from "react-i18next"
import { Check, ChevronDown } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import type { Cohort } from "@/types"

interface Props {
  status: Cohort["status"]
  disabled?: boolean
  onChange: (next: Cohort["status"]) => void
  /** Optional label for assistive tech, e.g. "Change cohort status". */
  ariaLabel?: string
}

const STATUS_ORDER: Cohort["status"][] = ["upcoming", "active", "completed"]

const STATUS_BADGE: Record<Cohort["status"], "success" | "info" | "muted"> = {
  upcoming: "info",
  active: "success",
  completed: "muted",
}

const STATUS_I18N_KEY: Record<Cohort["status"], string> = {
  upcoming: "admin.cohorts.statusUpcoming",
  active: "admin.cohorts.statusActive",
  completed: "admin.cohorts.statusCompleted",
}

/**
 * The cohort-status badge IS the status picker — no separate select alongside.
 *
 * Same pattern as ``RoleSelector``: the previous layout showed the current
 * status twice (a coloured pill in the page header AND a ``NativeSelect``
 * inside the Details card). One affordance, one place to click. Keyboard
 * works: ``Enter`` / ``Space`` opens the menu, arrows navigate, ``Esc``
 * closes.
 *
 * When ``disabled`` is true the badge renders flat without the dropdown
 * chevron, signalling read-only without changing layout. Moving from
 * ``active`` → ``completed`` is one-way in practice, but the confirm
 * happens in the parent so this component stays presentational.
 */
export function CohortStatusPicker({ status, disabled = false, onChange, ariaLabel }: Props) {
  const { t } = useTranslation()

  const badge = (
    <Badge
      variant={STATUS_BADGE[status]}
      className={cn(
        "gap-1.5 select-none capitalize",
        disabled && "cursor-default",
        !disabled &&
          "cursor-pointer transition-shadow hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      )}
    >
      {t(STATUS_I18N_KEY[status])}
      {!disabled && <ChevronDown className="h-3 w-3 opacity-70" strokeWidth={1.75} aria-hidden />}
    </Badge>
  )

  if (disabled) {
    return badge
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild aria-label={ariaLabel}>
        <button
          type="button"
          className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          {badge}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[10rem]">
        {STATUS_ORDER.map((value) => {
          const selected = value === status
          return (
            <DropdownMenuItem
              key={value}
              onSelect={() => {
                if (!selected) onChange(value)
              }}
              className={cn(
                "justify-between",
                selected && "font-medium text-foreground",
              )}
            >
              <span>{t(STATUS_I18N_KEY[value])}</span>
              {selected && (
                <Check className="h-3.5 w-3.5 text-primary" strokeWidth={1.75} aria-hidden />
              )}
            </DropdownMenuItem>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
