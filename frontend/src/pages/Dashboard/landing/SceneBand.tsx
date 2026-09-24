import type { ReactNode } from "react"

/**
 * A stage for the scenes that show something rather than say something.
 *
 * The page is one continuous backdrop, which is what makes the hero and the
 * claims work. It is also what made the tour, the shelf and the film look
 * like objects left floating in an empty room — «когда появляются
 * изображения и видео, они уже как-то висят в пустоте» — and, with every
 * block shorter than the screen, the reader resting on one could see the
 * edges of the two either side of it, so nothing read as a block at all.
 *
 * Two things fix that, and both are here.
 *
 * - **A band.** Full width, a tone lighter than the page, and frosted: the
 *   leaves keep moving behind it, blurred, so the scene does not stop — it
 *   passes behind glass. The band has edges, and the edges are what divide
 *   the page into blocks. claude.com does the same with tonal bands.
 * - **A full screen.** From `lg`, where the page has its rest stops, the
 *   band is at least one viewport tall with its content centred, so a reader
 *   resting on it sees this scene and nothing of its neighbours.
 *
 * Two tones, `raised` (lighter than the page) and `sunken` (darker, in both
 * themes), so that two staged scenes in a row — the tour and then the shelf
 * — still have an edge between them instead of merging into one long band.
 *
 * The band is also the scene's rest stop (`data-scene-stop`), so the page
 * settles with the band filling the screen exactly.
 *
 * Words — the hero, the claims, the close — stay on the open page. The
 * contrast between open scenes and staged ones is the rhythm.
 */
export function SceneBand({
  children,
  label,
  tone = "raised",
  className = "",
}: {
  children: ReactNode
  label?: string
  tone?: "raised" | "sunken"
  className?: string
}) {
  return (
    <section
      aria-label={label}
      data-scene-stop="center"
      className={
        "relative flex w-full flex-col justify-center py-16 backdrop-blur-2xl sm:py-20 lg:min-h-[100svh] lg:py-0 " +
        (tone === "raised" ? "bg-surface/80 " : "bg-muted/85 ") +
        className
      }
    >
      {children}
    </section>
  )
}
