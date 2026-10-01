import { useTranslation } from "react-i18next"

import { Checkbox } from "@/components/ui/checkbox"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { READING_SIZES, type ReadingPrefs, type ReadingSize } from "@/lib/readingPrefs"
import { cn } from "@/lib/utils"

const GLYPH_SIZE: Record<ReadingSize, string> = { s: "text-xs", m: "text-sm", l: "text-base", xl: "text-lg" }

/**
 * "Aa" beside a reading lesson: the text a size larger or smaller, and an
 * easy-reading mode with looser lines. The audience runs from teenagers to
 * grandparents, and the evening read on a phone is the main one.
 */
export function ReadingControls({ prefs, onChange }: { prefs: ReadingPrefs; onChange: (next: Partial<ReadingPrefs>) => void }) {
  const { t } = useTranslation()
  return (
    <Popover>
      <PopoverTrigger
        aria-label={t("chapter.reading.label")}
        className="ml-auto inline-flex h-7 items-center rounded-md border border-edge px-2 font-serif text-sm normal-case tracking-normal text-ink-muted transition-colors hover:bg-muted/40 hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <span aria-hidden>
          A<span className="text-xs">a</span>
        </span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 space-y-4">
        <div role="group" aria-label={t("chapter.reading.size")}>
          <p className="mb-2 text-xs font-medium text-ink-muted">{t("chapter.reading.size")}</p>
          <div className="grid grid-cols-4 gap-1">
            {READING_SIZES.map((size) => (
              <button
                key={size}
                type="button"
                aria-pressed={prefs.size === size}
                aria-label={t(`chapter.reading.sizes.${size}`)}
                onClick={() => onChange({ size })}
                className={cn(
                  "h-9 rounded-md border font-serif transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand",
                  GLYPH_SIZE[size],
                  prefs.size === size ? "border-brand bg-brand/10 text-ink" : "border-edge text-ink-muted hover:bg-muted/40",
                )}
              >
                <span aria-hidden>A</span>
              </button>
            ))}
          </div>
        </div>
        <label className="flex cursor-pointer items-start gap-2 text-sm">
          <Checkbox className="mt-0.5" checked={prefs.easy} onCheckedChange={(v) => onChange({ easy: v === true })} />
          <span>
            {t("chapter.reading.easy")}
            <span className="block text-xs text-ink-muted">{t("chapter.reading.easyHint")}</span>
          </span>
        </label>
      </PopoverContent>
    </Popover>
  )
}
