import { useEffect, useRef } from "react"
import { useReducedMotion } from "motion/react"

/**
 * Twenty seconds of the product working, silent and on a loop.
 *
 * Distinct from the film below it, and the difference decides how each one
 * behaves. The film is a minute with a voice: it is watched, so it waits
 * behind a poster with controls and starts only when somebody asks. This is
 * a caption that happens to move — a lesson switching language mid-screen —
 * so it plays by itself, mutes itself, and never shows a control.
 *
 * It starts when it reaches the viewport and pauses when it leaves. An
 * autoplaying video that keeps decoding while the reader is three sections
 * away is a battery cost with nobody watching, and on a phone it is the
 * difference between a warm device and a cold one.
 *
 * `playsInline` keeps iOS from hijacking it fullscreen, and `muted` is what
 * makes autoplay legal at all — every browser refuses to start audio nobody
 * asked for, and rightly.
 *
 * The poster is a frame from the tour itself, not the film's title card.
 * Both used `intro-poster.jpg` at first, which put the same Equip wordmark
 * on screen twice within one scroll — the page looked like it was
 * repeating itself rather than showing two different things.
 *
 * Under `prefers-reduced-motion` that poster frame is shown instead. The
 * captions are burnt into the frames, so a still of it still says what the
 * product does; a reader who has asked for less movement should not have to
 * choose between a seizure risk and the information.
 */
export function ProductTour() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const prefersReducedMotion = useReducedMotion()

  useEffect(() => {
    const video = videoRef.current
    if (!video || prefersReducedMotion) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          // `play()` rejects if the browser declines autoplay — that is a
          // decision, not a fault, and the poster stays up.
          void video.play().catch(() => {})
        } else {
          video.pause()
        }
      },
      { threshold: 0.25 },
    )

    observer.observe(video)
    return () => observer.disconnect()
  }, [prefersReducedMotion])

  if (prefersReducedMotion) {
    return (
      <section className="mx-auto w-full max-w-5xl px-4 sm:px-6">
        <img
          src="/video/tour-poster.jpg"
          alt=""
          width={1920}
          height={1080}
          className="w-full rounded-xl border border-line"
        />
      </section>
    )
  }

  return (
    <section className="mx-auto w-full max-w-5xl px-4 sm:px-6">
      <video
        ref={videoRef}
        className="w-full rounded-xl border border-line bg-surface"
        muted
        loop
        playsInline
        preload="metadata"
        poster="/video/tour-poster.jpg"
        width={1920}
        height={1080}
        aria-hidden
      >
        <source src="/video/tour.webm" type="video/webm" />
        <source src="/video/tour.mp4" type="video/mp4" />
      </video>
    </section>
  )
}
