import type { ReactNode } from "react"

/**
 * One scene of the landing page that shows something rather than says it:
 * the tour, the shelf, the film.
 *
 * From `lg` a scene is at least one screen tall with its content centred,
 * so a reader resting on it sees this scene and nothing of its neighbours'
 * edges. It is also the scene's rest stop (`data-scene-stop`), and it
 * tells the backdrop which pose to take
 * while it is on screen (`data-backdrop-pose`) — the leaves square into a
 * frame round the video, or lay themselves out along the shelf. See
 * `LandingBackdrop`.
 *
 * BELOW `lg` IT IS AS TALL AS WHAT IT HOLDS. The rest stops are a wheel
 * thing (`pageScroll.ts` never loads on a phone), so a full screen per
 * scene bought a phone nothing but air: the shelf is one row of covers
 * about 250px tall, and it sat in 844px of it — with the tour's band
 * above, nearly two empty screens between the tour and the covers. The
 * backdrop still frames each scene; it reads the element, not the band.
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
        "relative flex w-full flex-col justify-center py-14 lg:min-h-[100svh] lg:py-0 " +
        className
      }
    >
      {children}
    </section>
  )
}
