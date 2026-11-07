/**
 * Text written into a plain-text field, shown as the text it was meant to be.
 *
 * Assignment descriptions are typed into a textarea, yet four of the five on
 * the live site arrived with HTML in them — pasted from a lesson or brought in
 * by an import — and a student read «<p>Прочитайте книгу…</p>» with the tags
 * (2026-11-06). The stored words are the teacher's and stay as they are; this
 * only changes what a reader sees: paragraphs and line breaks become new
 * lines, every other tag goes. Nothing is rendered as HTML, so nothing in the
 * text can run.
 */
const MARKUP = /<\/?(?:p|br|div|span|strong|em|b|i|u|a|ul|ol|li|h[1-6]|blockquote)\b[^>]*>/i

export function asPlainText(text: string): string {
  if (!MARKUP.test(text)) return text
  const broken = text
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(?:p|div|li|h[1-6]|blockquote)>/gi, "\n")
  // DOMParser builds an inert document: no script in it runs, no image loads.
  const parsed = new DOMParser().parseFromString(broken, "text/html")
  // Their text is code, not words: dropped whole rather than shown.
  parsed.body.querySelectorAll("script, style, template, noscript").forEach((node) => node.remove())
  return (parsed.body.textContent ?? "").replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim()
}
