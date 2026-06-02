import { useTranslation } from "react-i18next"
import { Menu } from "lucide-react"
import { PressFeedback } from "@/components/motion"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

const ICON_STROKE = 1.75 as const

interface Props {
  onOpen: () => void
  isOpen: boolean
}

/**
 * Mobile-only hamburger button (< md). Tooltip duplicates the visible
 * label for screen readers + keyboard hover; the parent owns the open
 * state because closing on route change happens up there.
 */
export function HeaderMobileMenuTrigger({ onOpen, isOpen }: Props) {
  const { t } = useTranslation()
  return (
    <div className="flex md:hidden">
      <Tooltip>
        <TooltipTrigger asChild>
          <PressFeedback className="inline-flex">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 min-w-8 px-1 text-ink-muted hover:text-ink"
              onClick={onOpen}
              aria-label={t("header.menu")}
              aria-expanded={isOpen}
            >
              <Menu className="h-4 w-4" strokeWidth={ICON_STROKE} aria-hidden="true" />
            </Button>
          </PressFeedback>
        </TooltipTrigger>
        <TooltipContent side="bottom" sideOffset={8}>
          <p>{t("header.menu")}</p>
        </TooltipContent>
      </Tooltip>
    </div>
  )
}
