import { useTranslation } from "react-i18next"
import { Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  CHAPTER_TYPES,
  CHAPTER_TYPE_LABEL_KEYS,
  CHAPTER_TYPE_META,
  type ChapterType,
} from "@/lib/chapterTypes"

interface AddChapterBarProps {
  onAdd: (type: ChapterType) => void
  /** ``"empty"`` renders the prominent 4-card layout for the
   * EmptyState slot when the module has no chapters yet.
   * ``"compact"`` renders an inline row of 4 buttons below the
   * chapter list. */
  variant: "empty" | "compact"
}

/**
 * Replaces the old single "+ Add Chapter" button with four explicit
 * entry points, one per chapter type. Teachers decide what they're
 * creating up-front instead of creating a default-typed chapter and
 * then changing the type via a separate picker inside the chapter
 * editor — that picker was the friction the user wanted removed.
 *
 * The component carries the four buttons in a single source of
 * truth (``CHAPTER_TYPES``) so adding a fifth type ever in the
 * future means updating the central enum + i18n bundles, nothing
 * else.
 */
export function AddChapterBar({ onAdd, variant }: AddChapterBarProps) {
  const { t } = useTranslation()
  if (variant === "empty") {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {CHAPTER_TYPES.map((type) => {
          const Icon = CHAPTER_TYPE_META[type].icon
          return (
            <button
              key={type}
              type="button"
              onClick={() => onAdd(type)}
              className="group flex flex-col items-start gap-2 rounded-lg border border-dashed border-edge bg-card px-4 py-4 text-left transition-colors hover:border-brand/40 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2"
            >
              <div className="flex h-9 w-9 items-center justify-center rounded-md bg-muted text-ink-muted transition-colors group-hover:bg-brand/10 group-hover:text-brand-ink">
                <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
              </div>
              <div>
                <p className="text-sm font-medium text-ink">
                  {t(CHAPTER_TYPE_LABEL_KEYS[type])}
                </p>
                <p className="mt-0.5 text-xs text-ink-muted">
                  {t(`moduleEditor.addBar.${type}.description`)}
                </p>
              </div>
            </button>
          )
        })}
      </div>
    )
  }
  // ``compact`` — used below the chapter list. The 4 buttons sit in
  // a single horizontal flex container; on narrow viewports they
  // wrap to two rows of two.
  return (
    <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
      {CHAPTER_TYPES.map((type) => {
        const Icon = CHAPTER_TYPE_META[type].icon
        return (
          <Button
            key={type}
            variant="outline"
            onClick={() => onAdd(type)}
            className={cn(
              "h-12 flex-1 border-dashed text-sm font-medium sm:flex-none sm:px-4",
            )}
          >
            <Plus className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} aria-hidden="true" />
            <Icon className="h-3.5 w-3.5 mr-1.5 text-ink-muted" strokeWidth={1.75} aria-hidden="true" />
            {t(CHAPTER_TYPE_LABEL_KEYS[type])}
          </Button>
        )
      })}
    </div>
  )
}
