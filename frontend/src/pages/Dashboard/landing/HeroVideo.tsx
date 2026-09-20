/**
 * The minute that explains the platform — once there is one to show.
 *
 * Vadym is producing a roughly one-minute film: what Equip is, what problem
 * it solves. It is the centre of this page's argument, which is why the page
 * around it is three screens instead of nine: the film does the explaining
 * that the old wall of prose was doing badly.
 *
 * Until the file exists this renders **nothing**. Not a grey box, not a play
 * button over a placeholder, not "видео скоро" — a frame advertising a video
 * that will not play is worse than a page that never promised one, and the
 * landing page has enough history of showing invented stand-ins for real
 * things.
 *
 * TO TURN IT ON: drop the file in `public/video/` (an H.264 `.mp4` plays
 * everywhere; a `.webm` beside it saves bandwidth on Chrome and Firefox),
 * put a still frame next to it, and fill in the constant below. Nothing else
 * on the page has to change.
 *
 * The attributes are chosen for a film with a voice-over:
 *
 * - `controls` — it is a minute of speech, so a viewer must be able to
 *   pause, scrub and adjust volume. No autoplay: sound that starts by itself
 *   is the fastest way to lose the tab.
 * - `preload="none"` with a `poster` — the poster is a still, so an
 *   unstarted video costs one image instead of megabytes of unwatched film.
 * - `playsInline` — iOS otherwise hijacks the video into fullscreen.
 */

import { useTranslation } from "react-i18next"

import { Section } from "@/components/layout/Section"

type VideoSource = {
  /** Public path, e.g. `/video/equip-intro.mp4`. */
  src: string
  /** Still frame shown before playback, e.g. `/video/equip-intro.jpg`. */
  poster: string
  /** Optional WebM at the same duration, offered to browsers that take it. */
  webm?: string
  /** Sizing only — keeps the layout from jumping while the file loads. */
  width: number
  height: number
}

/** The film, delivered 2026-09-20. `null` would render the section away. */
const INTRO: VideoSource | null = {
  src: "/video/intro.mp4",
  poster: "/video/intro-poster.jpg",
  width: 1920,
  height: 1080,
}

export function HeroVideo() {
  const { t } = useTranslation()

  if (!INTRO) return null

  return (
    <Section as="section">
      {/* The film had no label at all: a player appeared at the end of the
          page and a visitor had to press play to find out what they were
          being offered. One line, and it reuses the closing question's
          subtitle rather than adding a string to translate four times. */}
      <h2 className="font-serif text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
        {t("common.appName")} — {t("footer.tagline")}
      </h2>
      <video
        className="mt-6 w-full rounded-xl border border-line bg-surface"
        controls
        playsInline
        preload="none"
        poster={INTRO.poster}
        width={INTRO.width}
        height={INTRO.height}
      >
        {INTRO.webm ? <source src={INTRO.webm} type="video/webm" /> : null}
        <source src={INTRO.src} type="video/mp4" />
      </video>
    </Section>
  )
}
