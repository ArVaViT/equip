import type { Cut } from "./phoneCut"

/**
 * The tour's two cuts, in a module of their own so the boot code can name the
 * poster without importing the landing page (`lib/warmRoute.ts` preloads the
 * phone poster — the landing's LCP image on a phone — before React renders).
 */
export const TOUR: { wide: Cut; phone: Cut } = {
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
