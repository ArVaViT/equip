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

// Since organizations hold roles (2026-10-03) the platform decides one
// thing here: platform staff or not. Teacher and director are held in an
// organization — appointed, invited, placed — and this badge shows the
// highest of them, read from the memberships; the server answers 422
// ``user.role_held_by_membership`` to any attempt to set them directly.
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
          "cursor-pointer transition-shadow hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
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
          className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
        >
          {badge}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-[12rem]">
        {/* What the person is, from their organizations — not a choice. */}
        <DropdownMenuItem disabled className="justify-between font-medium text-ink">
          <span>{t(ROLE_I18N_KEY[role])}</span>
          <Check className="h-3.5 w-3.5 text-brand" strokeWidth={1.75} aria-hidden />
        </DropdownMenuItem>
        <DropdownMenuItem
          // Not admin → admin; admin → back to what the memberships say
          // (the server re-reads them; "student" is the request, not the answer).
          onSelect={() => onChange(role === "admin" ? "student" : "admin")}
        >
          {role === "admin" ? t("admin.roleSelector.revokeAdmin") : t("admin.roleSelector.makeAdmin")}
        </DropdownMenuItem>
        <p className="max-w-[16rem] px-2 py-1.5 text-xs text-ink-muted">{t("admin.roleSelector.heldByMembership")}</p>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
