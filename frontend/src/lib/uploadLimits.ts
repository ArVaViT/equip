/**
 * What the Storage buckets actually accept.
 *
 * Mirrors `supabase/migrations/20260227031449_create_storage_buckets.sql`.
 * The bucket enforces these on the server; the client used to promise more
 * than that — a 10 MB image cap in the editor against a 5 MB bucket, a
 * ``.mp4`` in the materials picker against a bucket that only knows
 * ``audio/mp4`` — so a teacher's photo passed every check on screen and
 * failed in English a few seconds later. Keeping the numbers here, once,
 * lets every upload path check the same limits the server will.
 *
 * If a migration changes a bucket, change it here in the same PR.
 */

export const MB = 1024 * 1024

export interface BucketSpec {
  readonly maxBytes: number
  /** Exactly the bucket's `allowed_mime_types`. */
  readonly mimeTypes: readonly string[]
  /** Dot-prefixed extensions for the file picker; one per format above. */
  readonly extensions: readonly string[]
  /** Language-neutral labels for "Allowed: PDF, MP3, …". */
  readonly formatLabels: readonly string[]
}

/** Public bucket: covers and inline content images. */
export const COURSE_ASSETS: BucketSpec = {
  maxBytes: 5 * MB,
  mimeTypes: ["image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"],
  extensions: [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"],
  formatLabels: ["JPG", "PNG", "WebP", "GIF", "SVG"],
}

/** Private bucket: course materials and chapter file blocks. */
export const COURSE_MATERIALS: BucketSpec = {
  maxBytes: 50 * MB,
  mimeTypes: [
    "application/pdf",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
  ],
  extensions: [".pdf", ".mp3", ".m4a", ".ogg", ".wav", ".doc", ".docx", ".ppt", ".pptx", ".txt"],
  formatLabels: ["PDF", "MP3", "M4A", "OGG", "WAV", "DOC", "DOCX", "PPT", "PPTX", "TXT"],
}

/**
 * The `accept` attribute for a file input: the bucket's MIME types plus
 * their extensions. Both, because pickers disagree — macOS matches on
 * MIME, Windows on extension, and iOS uses the MIME list to decide whether
 * to transcode a photo before handing it over.
 */
export function acceptAttribute(spec: BucketSpec): string {
  return [...spec.mimeTypes, ...spec.extensions].join(",")
}

export function maxMb(spec: BucketSpec): number {
  return spec.maxBytes / MB
}

export function formatList(spec: BucketSpec): string {
  return spec.formatLabels.join(", ")
}

/**
 * What a browser calls a file is not always what the bucket calls it.
 * Chrome on a Mac reports an iPhone voice memo as ``audio/x-m4a``; the
 * bucket's list says ``audio/mp4`` for the same bytes. Windows still
 * hands out ``audio/mp3`` and ``image/jpg``. Every one of these is the
 * same format under a different name, and every one was a 415 from the
 * server — so they are folded onto the bucket's spelling before upload.
 * Nothing here widens what the bucket accepts.
 */
const MIME_ALIASES: Readonly<Record<string, string>> = {
  "audio/x-m4a": "audio/mp4",
  "audio/m4a": "audio/mp4",
  "audio/mp3": "audio/mpeg",
  "audio/x-mpeg": "audio/mpeg",
  "audio/mpeg3": "audio/mpeg",
  "audio/x-wav": "audio/wav",
  "audio/wave": "audio/wav",
  "audio/vnd.wave": "audio/wav",
  "application/ogg": "audio/ogg",
  "image/jpg": "image/jpeg",
  "image/pjpeg": "image/jpeg",
}

/** For a file the browser could not type at all (``type === ""``). */
const MIME_BY_EXTENSION: Readonly<Record<string, string>> = {
  pdf: "application/pdf",
  mp3: "audio/mpeg",
  m4a: "audio/mp4",
  ogg: "audio/ogg",
  oga: "audio/ogg",
  wav: "audio/wav",
  doc: "application/msword",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ppt: "application/vnd.ms-powerpoint",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  txt: "text/plain",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  gif: "image/gif",
  svg: "image/svg+xml",
}

/** The part of a file we need to reason about a type; `File` satisfies it. */
export interface FileLike {
  readonly name: string
  readonly type: string
}

function extensionOf(name: string): string {
  const idx = name.lastIndexOf(".")
  return idx === -1 ? "" : name.slice(idx + 1).toLowerCase()
}

/**
 * The MIME type the bucket would accept for this file, or `null` when
 * there is none — in which case the server will refuse it too, and the
 * caller should say so before spending the upload.
 */
export function resolveContentType(file: FileLike, spec: BucketSpec): string | null {
  const reported = (file.type.toLowerCase().split(";")[0] ?? "").trim()
  const candidates = [reported, MIME_ALIASES[reported]]
  if (reported === "" || reported === "application/octet-stream") {
    candidates.push(MIME_BY_EXTENSION[extensionOf(file.name)])
  }
  for (const type of candidates) {
    if (type && spec.mimeTypes.includes(type)) return type
  }
  return null
}

/**
 * An iPhone's default photo format. No bucket accepts it and no browser
 * can show it, so it deserves its own sentence rather than the generic
 * "format not supported" — the teacher needs to know it is the phone's
 * setting, not the file, that has to change. Checked by extension as
 * well as type: Chrome on Windows reports HEIC as ``""``.
 */
export function isHeic(file: FileLike): boolean {
  const type = file.type.toLowerCase()
  if (type === "image/heic" || type === "image/heif" || type === "image/heic-sequence" || type === "image/heif-sequence") {
    return true
  }
  const ext = extensionOf(file.name)
  return ext === "heic" || ext === "heif"
}
