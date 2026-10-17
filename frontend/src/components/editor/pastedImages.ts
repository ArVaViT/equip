import type { EditorView } from "@tiptap/pm/view";

/**
 * Pictures inside pasted HTML — a page of a Word document, a letter from
 * Outlook, a note from another editor.
 *
 * What arrives as `<img src>` is one of three things:
 *
 *  - an address the page can load (`https:`, a relative path, `blob:`) —
 *    left alone;
 *  - the picture itself as a `data:` URI — the editor's Image node refuses
 *    those (`allowBase64: false`, and the server's sanitizer would strip
 *    them anyway), so it used to vanish without a word. It is turned into
 *    a file here and shown from a `blob:` URL while it uploads through the
 *    same path as any other image, then swapped for the stored address;
 *  - a pointer the browser can never open: Word's `file:///…/clip_image001.png`
 *    in a temp folder, Outlook's `cid:`, Safari's `webkit-fake-url:`. Those
 *    became broken pictures. They are dropped, and counted, so the editor
 *    can say once that they must be added separately.
 */

/** Schemes an `<img>` in the editor can actually show. */
const LOADABLE = /^(https?:|blob:|\/|\.\/|\.\.\/)/i;

export interface PreparedPaste {
  html: string;
  /** `blob:` URL in the returned HTML → the file it stands for. */
  files: Map<string, File>;
  /** Pictures dropped because the browser cannot reach them. */
  skipped: number;
}

/** True when the HTML carries words, not only pictures. */
export function htmlHasText(html: string): boolean {
  if (!html) return false;
  const doc = new DOMParser().parseFromString(html, "text/html");
  return (doc.body.textContent ?? "").trim().length > 0;
}

const EXTENSIONS: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/gif": "gif",
  "image/webp": "webp",
};

/** A `data:image/…` URI as a File, or null when it is not a usable image. */
export function dataUriToFile(uri: string, index: number): File | null {
  const match = /^data:([^;,]*)((?:;[^;,]*)*),(.*)$/s.exec(uri);
  if (!match) return null;
  const mime = (match[1] || "").toLowerCase();
  if (!mime.startsWith("image/")) return null;
  const isBase64 = /;base64/i.test(match[2] ?? "");
  const payload = match[3] ?? "";
  let bytes: Uint8Array<ArrayBuffer>;
  try {
    if (isBase64) {
      const binary = atob(payload.replace(/\s+/g, ""));
      bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    } else {
      bytes = new Uint8Array(new TextEncoder().encode(decodeURIComponent(payload)));
    }
  } catch {
    return null;
  }
  if (bytes.length === 0) return null;
  const ext = EXTENSIONS[mime] ?? mime.slice("image/".length).replace(/[^a-z0-9]/g, "");
  return new File([bytes], `pasted-image-${index + 1}.${ext || "img"}`, { type: mime });
}

/**
 * Rewrite pasted HTML so every picture in it either loads or is gone.
 * Pure apart from minting `blob:` URLs; the caller owns them (upload, then
 * revoke) — see `useImageUpload`.
 */
export function preparePastedHtml(html: string): PreparedPaste {
  const files = new Map<string, File>();
  let skipped = 0;
  if (!/<img\b/i.test(html)) return { html, files, skipped };

  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll("img").forEach((img) => {
    const src = (img.getAttribute("src") ?? "").trim();
    if (LOADABLE.test(src)) return;
    if (!src) {
      // Nothing to show and nothing lost: not worth a message.
      img.remove();
      return;
    }
    if (/^data:/i.test(src)) {
      const file = dataUriToFile(src, files.size);
      if (file) {
        const url = URL.createObjectURL(file);
        files.set(url, file);
        img.setAttribute("src", url);
        return;
      }
    }
    skipped += 1;
    img.remove();
  });
  return { html: doc.body.innerHTML, files, skipped };
}

/**
 * Point every image whose `src` is `from` at `to`, or remove it when `to`
 * is null (the upload failed). Kept out of the undo history: the teacher
 * undoes the paste, not the address swap behind it.
 */
export function replaceImageSrc(view: EditorView, from: string, to: string | null): void {
  if (view.isDestroyed) return;
  const found: { pos: number; size: number; attrs: Record<string, unknown> }[] = [];
  view.state.doc.descendants((node, pos) => {
    if (node.type.name === "image" && node.attrs.src === from) {
      found.push({ pos, size: node.nodeSize, attrs: node.attrs });
    }
  });
  if (found.length === 0) return;
  const tr = view.state.tr;
  // From the end, so a removal never shifts a position still to visit.
  for (const { pos, size, attrs } of found.reverse()) {
    if (to) tr.setNodeMarkup(pos, undefined, { ...attrs, src: to });
    else tr.delete(pos, pos + size);
  }
  tr.setMeta("addToHistory", false);
  view.dispatch(tr);
}
