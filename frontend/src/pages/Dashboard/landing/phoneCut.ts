import { useSyncExternalStore } from "react"

/**
 * The phone cuts of both films, and which one a screen gets.
 *
 * Until 2026-09-27 a phone was shown the 16:9 films cropped to a 9:16 frame
 * with `object-cover` — «просто обрежь, до тех пор пока я не сделаю отдельных
 * видео для телефона». The crop kept the burnt-in caption and lost the rest:
 * the tour's closing «Equip» came out as «Eq…», and the lesson screens lost
 * both margins. Vadym has now cut both films vertically (1080×1920, same
 * lengths), so a phone gets its own file and nothing is cut away.
 *
 * WHY NOT `<source media>`. It picks the file, but not the poster — a
 * `poster` has no media query — so a phone would show the landscape still
 * and then play a portrait film. One flag chooses both, and the `<video>`
 * is keyed on it, because swapping `<source>` children does not make a
 * mounted element load again.
 *
 * WHY `useSyncExternalStore`. The flag is read on the first render, not in
 * an effect after it: the tour preloads its metadata, and deciding one frame
 * late would start a phone downloading the landscape file it is about to
 * throw away. jsdom has no `matchMedia` and gets the landscape cut.
 *
 * The line is `sm` (640px). A tablet held upright is wider than that and a
 * 16:9 frame fills it well; a phone held sideways is too, and gets the
 * landscape film, which is the one that fits it.
 */
const PHONE = "(max-width: 639px)"

function subscribe(onChange: () => void) {
  if (typeof window.matchMedia !== "function") return () => {}
  const query = window.matchMedia(PHONE)
  query.addEventListener("change", onChange)
  return () => query.removeEventListener("change", onChange)
}

function isPhone() {
  return typeof window.matchMedia === "function" && window.matchMedia(PHONE).matches
}

export function usePhoneCut(): boolean {
  return useSyncExternalStore(subscribe, isPhone, () => false)
}

export type Cut = {
  /** H.264 — plays everywhere. */
  mp4: string
  /** Optional VP9 at the same length, lighter on Chrome and Firefox. */
  webm?: string
  poster: string
  /** Sizing only — reserves the frame before the file loads. */
  width: number
  height: number
}

/**
 * Sizes a frame to its cut. A portrait film is as wide as the column, but
 * never so tall that it runs under the header on a short phone — the width
 * shrinks with it, so the picture is never cropped to fit.
 */
export function frameClass(phone: boolean) {
  return phone
    ? "mx-auto aspect-[9/16] w-[min(100%,calc(78svh*9/16))]"
    : "aspect-video w-full"
}
