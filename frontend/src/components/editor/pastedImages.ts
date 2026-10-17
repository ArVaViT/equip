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

/**
 * Uploads of pasted pictures, by the `blob:` URL that stands in for each
 * while it travels — resolving to the stored address, or null on failure.
 *
 * The `blob:` URL is in the editor's HTML from the moment of the paste, so
 * it is also in whatever the block saves meanwhile. While the editor is
 * open, the swap in `replaceImageSrc` fixes that on the next save; once the
 * teacher has left the lesson, there is no editor to swap in, and the block
 * was saved with an address that dies with the page. A save therefore asks
 * here first (`withUploadedImages`). Entries are kept after they settle: a
 * save of text taken before the swap can still come later, and a few short
 * strings per paste cost nothing.
 */
const pastedUploads = new Map<string, Promise<string | null>>();
const settledUploads = new Map<string, string | null>();

/** Record the upload behind a pasted picture's `blob:` URL. */
export function trackPastedUpload(blobUrl: string, upload: Promise<string | null>): void {
  const tracked = upload.then(
    (url) => {
      settledUploads.set(blobUrl, url);
      return url;
    },
    () => {
      settledUploads.set(blobUrl, null);
      return null;
    },
  );
  pastedUploads.set(blobUrl, tracked);
}

const BLOB_SRC = /<img\b[^>]*(?<![-\w])src="blob:/i;

/** How long a save waits for a picture still uploading before it leaves it
 *  out. An upload has no timeout of its own; a save must not hang on one —
 *  the editor's swap of the address, if it ever comes, is one more save. */
export const UPLOAD_WAIT_MS = 60_000;

/** Point or drop each `blob:` picture by what its upload came to. */
function rewriteBlobImages(html: string, resolve: (blobUrl: string) => string | null): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  doc.querySelectorAll('img[src^="blob:"]').forEach((img) => {
    const url = resolve(img.getAttribute("src") ?? "");
    if (url) img.setAttribute("src", url);
    else img.remove();
  });
  return doc.body.innerHTML;
}

/**
 * The HTML as it may be saved: every pasted picture at its stored address,
 * waiting for uploads still under way. A picture whose upload failed, or a
 * `blob:` this page never made (one kept in a draft from an earlier visit),
 * is dropped — it could never load for anybody. So is one still uploading
 * after `UPLOAD_WAIT_MS`.
 */
export async function withUploadedImages(html: string): Promise<string> {
  if (!BLOB_SRC.test(html)) return html;
  const doc = new DOMParser().parseFromString(html, "text/html");
  const urls = new Set<string>();
  doc.querySelectorAll('img[src^="blob:"]').forEach((img) => urls.add(img.getAttribute("src") ?? ""));
  let timer: ReturnType<typeof setTimeout> | undefined;
  await Promise.race([
    Promise.all([...urls].map((url) => pastedUploads.get(url))),
    new Promise((resolve) => (timer = setTimeout(resolve, UPLOAD_WAIT_MS))),
  ]);
  clearTimeout(timer);
  return rewriteBlobImages(html, (url) => settledUploads.get(url) ?? null);
}

/**
 * The same, for a page that is leaving and cannot wait: pictures still
 * uploading are left out rather than saved under an address that dies
 * with the page.
 */
export function withUploadedImagesNow(html: string): string {
  if (!BLOB_SRC.test(html)) return html;
  return rewriteBlobImages(html, (url) => settledUploads.get(url) ?? null);
}

/** Tests only: forget every tracked upload. */
export function resetPastedUploads(): void {
  pastedUploads.clear();
  settledUploads.clear();
}
