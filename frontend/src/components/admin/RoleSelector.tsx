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
import { ROLE_BADGE_VARIANT, ROLE_I18N_KEY } from "@/lib/roles"
import type { UserRole } from "@/types"

interface Props {
  role: UserRole
  disabled?: boolean
  onChange: (next: UserRole) => void
  /** Optional label for assistive tech, e.g. "Change role for John Doe". */
  ariaLabel?: string
}

const ROLE_ORDER: UserRole[] = ["student", "pending_teacher", "teacher", "admin"]

/**
 * The role badge IS the role picker — no separate select alongside.
 *
 * Replaces the previous ``<Badge /> + <NativeSelect />`` pair that
 * showed the current role twice (once as a coloured pill, once as the
 * selected option in the dropdown). One affordance, one place to
 * click. Keyboard works: ``Enter`` / ``Space`` opens the menu, arrows
 * navigate, ``Esc`` closes.
 *
 * When ``disabled`` is true (e.g. the actor is editing their own row)
 * the badge renders flat without the dropdown chevron, signalling
 * read-only without changing the layout of surrounding cells.
 */
export function RoleSelector({ role, disabled = false, onChange, ariaLabel }: Props) {
  const { t } = useTranslation()

  const badge = (
    <Badge
      variant={ROLE_BADGE_VARIANT[role]}
      className={cn(
        "gap-1.5 select-none",
        disabled && "cursor-default",
        !disabled &&
          "cursor-pointer transition-shadow hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      )}
    >
      {t(ROLE_I18N_KEY[role])}
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
      <DropdownMenuContent align="start" className="min-w-[12rem]">
        {ROLE_ORDER.map((value) => {
          const selected = value === role
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
              <span>{t(ROLE_I18N_KEY[value])}</span>
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
