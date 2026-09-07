import { supabase } from "@/lib/supabase"
import { type BucketSpec, COURSE_ASSETS, COURSE_MATERIALS, resolveContentType } from "@/lib/uploadLimits"

const AVATARS_BUCKET = "avatars"
const COURSE_ASSETS_BUCKET = "course-assets"
const COURSE_MATERIALS_BUCKET = "course-materials"

// Signed-URL TTL for on-demand downloads. One hour is plenty for a user to
// click → browser to start the download, and keeps blast radius tight if a
// URL leaks (e.g. copied from the address bar into a chat). We re-sign
// every time the link is clicked, so the secret can rotate without
// breaking anything in the DB.
const SIGNED_URL_TTL_SECONDS = 60 * 60

const MAX_SAFE_NAME_LEN = 100

/**
 * Cyrillic → Latin, one letter at a time.
 *
 * Supabase Storage accepts only ``[A-Za-z0-9_/!.*'() &$=@;:+,?-]`` in an
 * object key; a file called ``Проповедь_12_сентября.pdf`` was a 400
 * ``InvalidKey`` for every teacher who names files in their own language,
 * which is every teacher this product has. Replacing the letters with
 * ``_`` would have made the key legal and the list of materials useless —
 * that list shows the key, and every file would have read ``_______.pdf``.
 *
 * Not any one standard (they disagree on щ, ё and ъ). The aim is a name
 * the teacher recognises as their file, not a reversible encoding.
 * Ukrainian letters Russian lacks are included: it is the other language
 * the product ships in.
 */
const CYRILLIC_TO_LATIN: Readonly<Record<string, string>> = {
  "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh",
  "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
  "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
  "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
  "я": "ya",
  // Ukrainian
  "ґ": "g", "є": "ye", "і": "i", "ї": "yi",
}

function transliterate(name: string): string {
  let out = ""
  for (const ch of name) {
    const lower = ch.toLowerCase()
    const latin = CYRILLIC_TO_LATIN[lower]
    if (latin === undefined) {
      out += ch
    } else if (ch === lower) {
      out += latin
    } else {
      out += latin.charAt(0).toUpperCase() + latin.slice(1)
    }
  }
  return out
}

/**
 * Turn a file name into a safe object-key segment: transliterate
 * Cyrillic, replace everything else outside ``[A-Za-z0-9._()-]`` with
 * ``_`` (path separators, quotes, whitespace, emoji, any other script),
 * collapse runs of ``_``, then cap the length without losing the
 * extension.
 *
 * The allowed set is narrower than what Storage tolerates on purpose:
 * ``&``, ``+``, ``;`` and ``=`` are legal in a key and a nuisance in a
 * signed URL, and nobody misses them in ``Q_A.pdf``.
 *
 * The length cap truncates the stem and re-appends the extension. The
 * version before it sliced to 100 chars *after* the replacement, which
 * silently dropped the trailing ``.pdf`` / ``.png`` on any long name and
 * produced extensionless keys (broken MIME sniffing / download UX).
 *
 * Exported only so the unit test can exercise the cases directly —
 * runtime callers should use the upload functions below.
 */
export function sanitizeFileName(name: string): string {
  const cleaned = transliterate(name)
    .replace(/[^A-Za-z0-9._()-]/gu, "_")
    .replace(/_+/g, "_")
  if (cleaned.length <= MAX_SAFE_NAME_LEN) return cleaned

  const dotIdx = cleaned.lastIndexOf(".")
  // No extension to preserve (or trailing dot) → hard truncate.
  if (dotIdx <= 0 || dotIdx === cleaned.length - 1) {
    return cleaned.slice(0, MAX_SAFE_NAME_LEN)
  }
  const ext = cleaned.slice(dotIdx)
  // Pathological case: extension itself is longer than the cap. Drop the
  // extension rather than emit a zero-length stem.
  if (ext.length >= MAX_SAFE_NAME_LEN) {
    return cleaned.slice(0, MAX_SAFE_NAME_LEN)
  }
  return cleaned.slice(0, MAX_SAFE_NAME_LEN - ext.length) + ext
}

/**
 * The file with the MIME type the bucket will accept for it.
 *
 * storage-js sends a `File` as a multipart part and takes the part's
 * Content-Type from the File itself — the `contentType` upload option is
 * ignored for Blob bodies — so an iPhone voice memo Chrome calls
 * ``audio/x-m4a`` reached the bucket under that name and was a 415,
 * although the bucket accepts the same bytes as ``audio/mp4``. A `File`
 * built from another `File` shares the bytes; nothing is copied.
 *
 * A type the bucket cannot accept is left alone: the server's refusal is
 * the honest answer there, and `preflightUpload` already said so before
 * the request when it could.
 */
function withBucketContentType(file: File, spec: BucketSpec): File {
  const type = resolveContentType(file, spec)
  if (type === null || type === file.type) return file
  return new File([file], file.name, { type, lastModified: file.lastModified })
}

function fileExtension(name: string, fallback: string = "jpg"): string {
  // ``name.split(".").pop()`` returned the whole filename on
  // extension-less inputs ("avatar" → "avatar"), producing weird
  // paths like ``avatar.avatar``. Use last-dot position so we only
  // treat as an extension what's actually after a separator, and
  // fall through to ``fallback`` when there is none.
  const idx = name.lastIndexOf(".")
  if (idx === -1 || idx === name.length - 1) return fallback
  return name.slice(idx + 1)
}

/**
 * Return a same-origin `/img/{bucket}/{path}` URL for public-bucket objects.
 * Vercel rewrites and Vite dev proxy map this to the Supabase Storage public
 * endpoint. Keeping the host the same bypasses AdBlock-style filters. The
 * path is used directly (no double URL-encoding); Supabase Storage expects
 * uploaded object keys as-is in the URL path.
 */
function getPublicUrl(bucket: string, path: string): string {
  return `/img/${bucket}/${path}`
}

/**
 * Upload to a public bucket with upsert semantics and return the
 * proxied public URL. Shared between avatar and cover-image uploads,
 * which differ only in bucket + path template.
 */
async function uploadToPublicBucket(
  bucket: string,
  path: string,
  file: File,
): Promise<string> {
  const { error } = await supabase.storage.from(bucket).upload(path, file, { upsert: true })
  if (error) throw error
  return getPublicUrl(bucket, path)
}

/**
 * Mint a short-lived signed URL for a private-bucket object. Shared
 * between course-material downloads (always `course-materials`) and
 * chapter file blocks (bucket varies per-block).
 */
async function createSignedDownloadUrl(bucket: string, path: string): Promise<string> {
  const { data, error } = await supabase.storage
    .from(bucket)
    .createSignedUrl(path, SIGNED_URL_TTL_SECONDS)
  if (error) throw error
  return data.signedUrl
}

interface UploadedBlockFile {
  bucket: string
  path: string
  name: string
}

export const storageService = {
  async uploadAvatar(userId: string, file: File): Promise<string> {
    const path = `${userId}/avatar.${fileExtension(file.name)}`
    return uploadToPublicBucket(AVATARS_BUCKET, path, file)
  },

  async uploadCourseImage(courseId: string, file: File): Promise<string> {
    const path = `${courseId}/cover.${fileExtension(file.name)}`
    return uploadToPublicBucket(COURSE_ASSETS_BUCKET, path, withBucketContentType(file, COURSE_ASSETS))
  },

  /**
   * Upload a course material file into the private `course-materials` bucket.
   * Returns nothing — every caller refreshes its own list afterwards and
   * signs URLs on demand via `getSignedMaterialUrl`. Previously this minted
   * a 1-year signed URL as a workaround for short TTLs; that bandaid is
   * gone now that chapter file blocks re-sign on click too.
   */
  async uploadCourseMaterial(courseId: string, file: File): Promise<void> {
    const timestamp = Date.now()
    const safeName = sanitizeFileName(file.name)
    const path = `${courseId}/${timestamp}-${safeName}`

    const { error } = await supabase.storage
      .from(COURSE_MATERIALS_BUCKET)
      .upload(path, withBucketContentType(file, COURSE_MATERIALS))

    if (error) throw error
  },

  async listCourseMaterials(courseId: string): Promise<{ name: string; path: string; size: number | undefined; created: string | null }[]> {
    const { data, error } = await supabase.storage
      .from(COURSE_MATERIALS_BUCKET)
      .list(courseId, { sortBy: { column: "created_at", order: "desc" } })

    if (error) throw error
    // `list` returns the folder's children, and a chapter that has a file
    // block is a sub-folder here (`{courseId}/{chapterId}/…`). Storage
    // marks folders with `id: null`; without this filter the teacher and
    // every student saw a "material" named after a chapter's UUID that
    // could not be downloaded.
    return (data ?? [])
      .filter((f) => f.id !== null)
      .map((f) => ({
        name: f.name,
        path: `${courseId}/${f.name}`,
        size: f.metadata?.size as number | undefined,
        created: f.created_at,
      }))
  },

  async getSignedMaterialUrl(path: string): Promise<string> {
    return createSignedDownloadUrl(COURSE_MATERIALS_BUCKET, path)
  },

  async deleteCourseMaterial(path: string): Promise<void> {
    const { error } = await supabase.storage
      .from(COURSE_MATERIALS_BUCKET)
      .remove([path])

    if (error) throw error
  },

  /**
   * Upload a file attached to a chapter block. The caller persists the
   * returned `{ bucket, path, name }` on the block and re-signs the URL
   * every time a student opens the file. Nothing JWT-secret-dependent
   * is ever stored in the database, so rotating the Supabase JWT secret
   * doesn't invalidate anything.
   */
  async uploadBlockFile(courseId: string, chapterId: string, file: File): Promise<UploadedBlockFile> {
    const timestamp = Date.now()
    const safeName = sanitizeFileName(file.name)
    // First path segment MUST be the course id: the `course-materials`
    // bucket's RLS policy (`course_materials_enrolled_read`) authorises a
    // download by matching `foldername[1]` against the caller's enrolment /
    // course ownership. A chapter-id-first path (the old shape) matches no
    // course, so enrolled students got a 400 when signing the file.
    const path = `${courseId}/${chapterId}/${timestamp}-${safeName}`

    const { error } = await supabase.storage
      .from(COURSE_MATERIALS_BUCKET)
      .upload(path, withBucketContentType(file, COURSE_MATERIALS))

    if (error) throw error

    return { bucket: COURSE_MATERIALS_BUCKET, path, name: file.name }
  },

  /** Mint a short-lived signed URL for a block-attached file. */
  async getSignedBlockFileUrl(bucket: string, path: string): Promise<string> {
    return createSignedDownloadUrl(bucket, path)
  },

  async uploadContentImage(file: File): Promise<string> {
    const ext = fileExtension(file.name)
    // ``Math.random()`` is non-cryptographic and worse:
    // ``toString(36).slice(2, 10)`` shortens it to ~8 base-36 chars,
    // so two simultaneous uploads in the same ms can collide. The
    // bucket uses ``upsert: false`` so the second upload errors —
    // visible as a confusing "upload failed" toast for the user.
    // ``crypto.randomUUID().slice(0, 8)`` is the same byte budget,
    // collision-resistant.
    const random = crypto.randomUUID().slice(0, 8)
    const path = `content-images/${Date.now()}-${random}.${ext}`

    // Content images use upsert: false so the random suffix prevents
    // overwriting an existing path; `uploadToPublicBucket` would upsert.
    const { error } = await supabase.storage
      .from(COURSE_ASSETS_BUCKET)
      .upload(path, withBucketContentType(file, COURSE_ASSETS))
    if (error) throw error
    return getPublicUrl(COURSE_ASSETS_BUCKET, path)
  },
}
