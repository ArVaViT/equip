/**
 * Is this page open inside another app's built-in browser?
 *
 * Google refuses to sign anybody in from an embedded web view
 * (`403: disallowed_useragent`). A link to Equip tapped in Instagram,
 * Facebook, Messenger, LinkedIn, TikTok or Line opens in exactly such a view,
 * and the Google button there is a dead end that looks like our fault. The
 * page cannot leave the view by itself; what it can do is say so before the
 * tap.
 *
 * Deliberately narrow. An app named in the user agent, or Android's own
 * WebView marker (`; wv)`). Telegram, WhatsApp and Gmail open links in the
 * system browser or a browser tab Google accepts, and an iOS home-screen web
 * app also lacks the `Safari/` token — guessing from that absence would warn
 * people whose Google button works.
 */
const IN_APP = /FBAN|FBAV|FB_IAB|Instagram|LinkedInApp|BytedanceWebview|musical_ly|\bLine\/|Snapchat|; wv\)/

export function isInAppBrowser(userAgent: string = typeof navigator === "undefined" ? "" : navigator.userAgent): boolean {
  return IN_APP.test(userAgent)
}
