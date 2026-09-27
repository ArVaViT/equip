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
 *
 * NO HEADING. One was added and taken straight back out: the poster is now
 * a frame of the product with its own caption burnt in, so a line of type
 * above it was labelling something that already introduces itself.
 */

import { Section } from "@/components/layout/Section";

import { SceneBand } from "./SceneBand"
import { frameClass, usePhoneCut, type Cut } from "./phoneCut";
import { ScrollScale } from "./ScrollScale";

/**
 * The film, delivered 2026-09-20; its phone cut, 2026-09-27. `null` would
 * render the section away.
 */
const INTRO: { wide: Cut; phone: Cut } | null = {
  wide: {
    mp4: "/video/intro.mp4",
    poster: "/video/intro-poster.jpg",
    width: 1920,
    height: 1080,
  },
  phone: {
    mp4: "/video/intro-vertical.mp4",
    poster: "/video/intro-poster-vertical.jpg",
    width: 1080,
    height: 1920,
  },
};

export function HeroVideo() {
  const phone = usePhoneCut();
  if (!INTRO) return null;
  const cut = phone ? INTRO.phone : INTRO.wide;

  return (
    // A scene of its own; the backdrop squares into a frame round it.
    <SceneBand pose="frame">
      <Section as="div" className="py-0">
        <div>
          <ScrollScale>
            <video
              // Keyed on the cut: a new `<source>` alone does not reload a
              // mounted element (see `phoneCut.ts`).
              key={cut.mp4}
              data-backdrop-target
              className={`block rounded-xl border border-line shadow-[0_40px_90px_-40px_hsl(var(--accent)/0.6)] bg-surface object-cover ${frameClass(phone)}`}
              controls
              playsInline
              preload="none"
              poster={cut.poster}
              width={cut.width}
              height={cut.height}
            >
              {cut.webm ? <source src={cut.webm} type="video/webm" /> : null}
              <source src={cut.mp4} type="video/mp4" />
            </video>
          </ScrollScale>
        </div>
      </Section>
    </SceneBand>
  );
}
