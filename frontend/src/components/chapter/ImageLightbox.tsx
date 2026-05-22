import { useEffect } from "react"
import { createPortal } from "react-dom"
import { X } from "lucide-react"
import { useTranslation } from "react-i18next"

interface ImageLightboxProps {
  src: string
  alt?: string
  onClose: () => void
}

/**
 * Fullscreen overlay that displays a single chapter image at the
 * largest size the viewport allows. Mounted via portal so it sits
 * above any sticky toolbars, navigation, or modals the chapter
 * page renders. Closes on:
 *
 *   - Click on the dim backdrop
 *   - Click on the explicit close button
 *   - ``Escape`` key
 *
 * Inline ``<img onClick>`` inside ``ChapterView``'s prose surface
 * opens this; nothing else triggers it.
 */
export function ImageLightbox({ src, alt, onClose }: ImageLightboxProps) {
  const { t } = useTranslation()

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    // ``overflow-hidden`` on body prevents the page scrolling behind
    // the overlay — feels glued to the foreground instead of
    // ghosting over scrolling content.
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    document.addEventListener("keydown", handleKey)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener("keydown", handleKey)
    }
  }, [onClose])

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("chapter.imageLightbox.dialogAria")}
      onClick={onClose}
      // ``z-[60]`` sits above the toolbar's z-20 and the modal
      // (z-50) that the rest of the app uses; the chapter image
      // lightbox is the highest meaningful surface.
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm animate-fade-in"
    >
      <button
        type="button"
        aria-label={t("chapter.imageLightbox.closeAria")}
        onClick={(e) => {
          e.stopPropagation()
          onClose()
        }}
        className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
      >
        <X className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
      </button>
      <img
        src={src}
        alt={alt ?? ""}
        // Block clicks on the image from bubbling to the backdrop
        // and closing the overlay; only the backdrop / X / Escape
        // close it.
        onClick={(e) => e.stopPropagation()}
        className="max-h-[92vh] max-w-[92vw] rounded-md shadow-2xl"
      />
    </div>,
    document.body,
  )
}
