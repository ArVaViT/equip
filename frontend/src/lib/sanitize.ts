import DOMPurify from "dompurify"
import { rewriteHtmlImageSources } from "./images"

/**
 * YouTube embed URLs we allow iframes to point at. Any other iframe is
 * removed outright — no arbitrary iframing of third-party origins.
 */
const YT_EMBED_PREFIXES = [
  "https://www.youtube.com/embed/",
  "https://www.youtube-nocookie.com/embed/",
] as const

// Module-scope code runs once per process, so the hooks only register once.
DOMPurify.addHook("uponSanitizeElement", (node, data) => {
  if (data.tagName === "iframe") {
    const src = (node as HTMLIFrameElement).getAttribute("src") || ""
    if (YT_EMBED_PREFIXES.some((p) => src.startsWith(p))) {
      return
    }
    node.parentNode?.removeChild(node)
  }
})

// Strip any href/src whose scheme is dangerous. DOMPurify already blocks
// javascript:, but we also block data: (outside of images handled via the
// proxy below), vbscript: and file: just in case.
DOMPurify.addHook("uponSanitizeAttribute", (_node, data) => {
  const name = data.attrName
  const value = (data.attrValue || "").trim().toLowerCase()
  if (name === "href" || name === "src" || name === "xlink:href") {
    if (
      value.startsWith("javascript:") ||
      value.startsWith("vbscript:") ||
      value.startsWith("file:") ||
      (value.startsWith("data:") && !value.startsWith("data:image/"))
    ) {
      data.keepAttr = false
    }
  }
  if (name.startsWith("on")) {
    data.keepAttr = false
  }
})

const SANITIZE_CONFIG = {
  // ``details`` + ``summary`` carry the chapter-renderer rewrite of the
  // toggle-callout block (see ``frontend/src/lib/callout-toggle.ts``).
  // Naming them explicitly keeps the dependency stable if a future
  // DOMPurify upgrade tightens its built-in HTML5 allowlist.
  ADD_TAGS: ["iframe", "details", "summary"],
  // ``data-type`` / ``data-latex`` / ``data-display`` carry the math
  // marker shape from ``@aarkue/tiptap-math-extension``; the renderer
  // walks ``span[data-type="inlineMath"]`` and feeds the LaTeX to
  // KaTeX. Without these attrs in ``ADD_ATTR`` DOMPurify drops them,
  // leaving the literal ``$x^2$`` delimiter span behind instead of
  // a rendered formula.
  ADD_ATTR: [
    "allow", "allowfullscreen", "frameborder", "src", "loading",
    "referrerpolicy", "data-callout", "data-youtube-embed",
    "data-type", "data-latex", "data-display",
    "alt", "width", "height",
  ],
  // Explicitly whitelist safe URI schemes; anything else gets stripped.
  ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,
  FORBID_TAGS: ["style", "form", "input", "button"],
  FORBID_ATTR: ["style", "onerror", "onload", "onclick", "onmouseover", "onfocus", "onblur"],
} satisfies Parameters<typeof DOMPurify.sanitize>[1]

export function sanitizeHtml(html: string): string {
  const cleaned = DOMPurify.sanitize(html, SANITIZE_CONFIG) as unknown as string
  return rewriteHtmlImageSources(cleaned)
}
