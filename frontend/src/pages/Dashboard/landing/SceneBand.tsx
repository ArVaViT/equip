import type { ReactNode } from "react"

/**
 * One scene of the landing page that shows something rather than says it:
 * the tour, the shelf, the film.
 *
 * From `lg`, where the page has its rest stops, a scene is at least one
 * screen tall with its content centred, so a reader resting on it sees this
 * scene and nothing of its neighbours' edges. It is also the scene's rest
 * stop (`data-scene-stop`), and it tells the backdrop which pose to take
 * while it is on screen (`data-backdrop-pose`) — the leaves square into a
 * frame round the video, or lay themselves out along the shelf. See
 * `LandingBackdrop`.
 *
 * NO BACKGROUND. For one afternoon this was a frosted band a tone off the
 * page. It divided the page, but by covering the one thing that moves: «ты
 * просто добавляешь фон под блоки … глухой фон лучше не делает». What
 * marks a block now is the scene itself, gathering round it.
 */
export function SceneBand({
  children,
  label,
  pose,
  className = "",
}: {
  children: ReactNode
  label?: string
  pose?: "frame" | "row"
  className?: string
}) {
  return (
    <section
      aria-label={label}
      data-scene-stop="center"
      data-backdrop-pose={pose}
      className={
        "relative flex w-full flex-col justify-center py-16 sm:py-20 lg:min-h-[100svh] lg:py-0 " +
        className
      }
    >
      {children}
    </section>
  )
}
