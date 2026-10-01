import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { X } from "lucide-react"

import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover"
import type { Passage } from "@/services/scripture"

/**
 * The verse a lesson cites, over the lesson, in the reader's own Bible.
 *
 * Opened from a reference button inside a block's injected HTML, so there is
 * no React trigger to hang it on: the button is the anchor, by reference.
 * Closing returns focus to that button, which Radix does only for its own
 * triggers.
 */
export function VerseCard({
  anchor,
  passage,
  onClose,
}: {
  anchor: HTMLElement
  passage: Passage
  onClose: () => void
}) {
  const { t } = useTranslation()
  const virtualRef = useMemo(() => ({ current: anchor }), [anchor])

  return (
    <Popover open onOpenChange={(open) => !open && onClose()}>
      <PopoverAnchor virtualRef={virtualRef} />
      <PopoverContent
        align="center"
        collisionPadding={16}
        className="w-[min(22rem,calc(100vw-2rem))] space-y-2"
        aria-label={passage.written}
        onCloseAutoFocus={(e) => {
          e.preventDefault()
          anchor.focus()
        }}
      >
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm font-semibold text-ink">{passage.written}</p>
          <button
            type="button"
            onClick={onClose}
            aria-label={t("common.close")}
            className="-mr-1 -mt-1 rounded p-1 text-ink-muted transition-colors hover:text-ink"
          >
            <X className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
          </button>
        </div>
        <p className="max-h-[50vh] overflow-y-auto font-serif text-base leading-relaxed text-ink">{passage.text}</p>
        {passage.edition && (
          <p className="text-xs text-ink-muted">{t(`scripture.edition.${passage.edition}`, { defaultValue: "" })}</p>
        )}
      </PopoverContent>
    </Popover>
  )
}
