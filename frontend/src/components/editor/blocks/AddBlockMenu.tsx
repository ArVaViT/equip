import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Loader2, Plus } from "lucide-react"

import { cn } from "@/lib/utils"
import { useDropdownPosition } from "@/components/editor/useDropdownPosition"
import { BLOCK_TYPE_LABEL_KEYS, BLOCK_TYPES, type BlockType } from "./types"

interface Props {
  onAdd: (type: BlockType) => void
  adding: boolean
}

/**
 * "Add Block" button with a dropdown of block types. Self-contained —
 * the parent just exposes an ``onAdd(type)`` callback.
 *
 * Follows the same dropdown discipline as the toolbar dropdowns in
 * ``components/editor/`` (Callout / Table / Code Block):
 *
 *  - ``aria-haspopup="menu"`` + ``aria-expanded`` on the trigger
 *  - ``role="menu"`` on the panel, ``role="menuitem"`` on each option
 *  - click-outside closes
 *  - Escape closes
 *  - viewport-aware horizontal anchor (flips to ``right-0`` near
 *    the right edge of the viewport)
 */
export function AddBlockMenu({ onAdd, adding }: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  // Panel inherits its parent's width (``w-full`` on the trigger
  // container in the layout above), but the overflow check needs a
  // concrete number — pass a sensible fallback that matches the
  // smallest the panel can realistically be.
  const { alignClass } = useDropdownPosition(open, triggerRef, 240)

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleEscape)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleEscape)
    }
  }, [open])

  const pick = (type: BlockType) => {
    setOpen(false)
    onAdd(type)
  }

  return (
    <div className="relative" ref={containerRef}>
      <Button
        ref={triggerRef}
        variant="outline"
        size="sm"
        className="w-full border-dashed"
        onClick={() => setOpen((v) => !v)}
        disabled={adding}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {adding ? (
          <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" strokeWidth={1.75} aria-hidden="true" />
        ) : (
          <Plus className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} aria-hidden="true" />
        )}
        {t("blockEditor.addBlock")}
      </Button>
      {open && (
        <div
          role="menu"
          aria-label={t("blockEditor.addBlock")}
          className={cn(
            "absolute top-full z-20 mt-1 w-full min-w-[240px] rounded-md border bg-surface py-1 shadow-lg",
            alignClass,
          )}
        >
          {BLOCK_TYPES.map((bt) => {
            const Icon = bt.icon
            return (
              <button
                key={bt.value}
                type="button"
                role="menuitem"
                onClick={() => pick(bt.value)}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-muted text-left focus-visible:outline-none focus-visible:bg-muted"
              >
                <Icon className="h-4 w-4 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
                {t(BLOCK_TYPE_LABEL_KEYS[bt.value])}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
