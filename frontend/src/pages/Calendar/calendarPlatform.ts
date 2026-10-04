/**
 * Which calendar this device most likely keeps, from the user agent.
 *
 * An Android phone's calendar is Google; an iPhone's and a Mac's is
 * Apple's. The dialog puts that one first and solid, so the common case
 * is one tap. Anything else — a Windows laptop, a Linux desktop, a user
 * agent that says nothing — keeps the Apple/Outlook link first, because
 * `webcal:` is the one that opens whatever desktop calendar is installed.
 */
export function calendarPlatform(userAgent: string): "android" | "apple" | "other" {
  if (/Android/i.test(userAgent)) return "android"
  if (/iPhone|iPad|iPod|Macintosh/i.test(userAgent)) return "apple"
  return "other"
}
