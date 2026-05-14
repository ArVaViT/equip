import api from "./api"

export interface VerseOfTheDay {
  reference: string
  text: string
  version: string
  locale: "en" | "ru"
  date: string
}

/**
 * Today's curated devotional verse in the caller's locale. Backed by a
 * 250-entry rotation on the server. The endpoint is intentionally
 * 404-friendly — when the upstream Bible API is unconfigured or down,
 * the dashboard hides the card rather than blocking the page.
 */
export const verseOfTheDayService = {
  async get(locale: "en" | "ru"): Promise<VerseOfTheDay> {
    const { data } = await api.get<VerseOfTheDay>("/verse-of-the-day", {
      params: { locale },
    })
    return data
  },
}
