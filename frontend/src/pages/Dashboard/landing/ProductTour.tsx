import { useEffect, useRef } from "react";
import { useReducedMotion } from "motion/react";

import { SceneBand } from "./SceneBand"
import { frameClass, usePhoneCut, type Cut } from "./phoneCut";
import { ScrollScale } from "./ScrollScale";

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
const TOUR: { wide: Cut; phone: Cut } = {
  wide: {
    mp4: "/video/tour.mp4",
    webm: "/video/tour.webm",
    poster: "/video/tour-poster.jpg",
    width: 1920,
    height: 1080,
  },
  // Cut for the phone, 2026-09-27. Its poster is the closing wordmark
  // rather than a lesson screen: the film's phone poster is already the
  // lesson, and the rule above holds on a phone too — two different frames.
  phone: {
    mp4: "/video/tour-vertical.mp4",
    webm: "/video/tour-vertical.webm",
    poster: "/video/tour-poster-vertical.jpg",
    width: 1080,
    height: 1920,
  },
};

export function ProductTour() {
  const phone = usePhoneCut();
  const cut = phone ? TOUR.phone : TOUR.wide;
  const videoRef = useRef<HTMLVideoElement>(null);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    const video = videoRef.current;
    if (!video || prefersReducedMotion) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          // `play()` rejects if the browser declines autoplay — that is a
          // decision, not a fault, and the poster stays up.
          void video.play().catch(() => {});
        } else {
          video.pause();
        }
      },
      { threshold: 0.25 },
    );

    observer.observe(video);
    return () => observer.disconnect();
    // `cut`: a new cut is a new element, which needs observing afresh.
  }, [prefersReducedMotion, cut]);

  if (prefersReducedMotion) {
    return (
      <SceneBand pose="frame">
        <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
          <img
            src={cut.poster}
            alt=""
            width={cut.width}
            height={cut.height}
            className={`block rounded-xl border border-line shadow-[0_40px_90px_-40px_hsl(var(--accent)/0.6)] object-cover ${frameClass(phone)}`}
          />
        </div>
      </SceneBand>
    );
  }

  // A scene of its own; the backdrop squares into a frame round it.
  return (
    <SceneBand pose="frame">
      <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
        <ScrollScale>
          <video
            key={cut.mp4}
            data-backdrop-target
            ref={videoRef}
            className={`block rounded-xl border border-line shadow-[0_40px_90px_-40px_hsl(var(--accent)/0.6)] bg-surface object-cover ${frameClass(phone)}`}
            muted
            loop
            playsInline
            preload="metadata"
            poster={cut.poster}
            width={cut.width}
            height={cut.height}
            aria-hidden
          >
            {cut.webm ? <source src={cut.webm} type="video/webm" /> : null}
            <source src={cut.mp4} type="video/mp4" />
          </video>
        </ScrollScale>
      </div>
    </SceneBand>
  );
}
