import { refuseWhileViewingAs } from "@/lib/viewAs"
import { SUPABASE_ANON_KEY, SUPABASE_URL, supabase } from "@/lib/supabase"
import {
  type BucketSpec,
  COURSE_ASSETS,
  COURSE_MATERIALS,
  ORGANIZATION_LOGOS,
  SUBMISSIONS,
  resolveContentType,
} from "@/lib/uploadLimits"

const AVATARS_BUCKET = "avatars"
const COURSE_ASSETS_BUCKET = "course-assets"
const COURSE_MATERIALS_BUCKET = "course-materials"
const ORGANIZATION_LOGOS_BUCKET = "organization-logos"
const SUBMISSIONS_BUCKET = "submissions"
const LOGO_EXTENSION: Record<string, string> = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
  "image/gif": "gif",
}

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
 * Upload to a public bucket under a fresh key and return the proxied
 * public URL. Shared between avatar and cover-image uploads, which
 * differ only in bucket + path template.
 *
 * Two reasons this writes a new key instead of overwriting the old one.
 *
 * **It could not overwrite.** `upsert: true` makes Storage look for an
 * existing object first, and that lookup runs under RLS. Migration
 * 20260421010827 dropped `avatars_public_read` and
 * `course_assets_public_read` — correctly, they granted listing of every
 * file in the bucket — and left neither bucket with any SELECT policy at
 * all. Public URLs kept working, because a public bucket serves those
 * without RLS. Replacing a file stopped: the lookup sees nothing, the
 * insert that follows collides, and Storage answers "new row violates
 * row-level security policy", which points at the wrong half of what
 * just happened. Verified on production 2026-09-09: as `authenticated`
 * with a teacher's claims, `storage.objects` shows zero rows in
 * `course-assets`.
 *
 * **It should not overwrite anyway.** Both buckets are public and
 * Storage serves public objects with a one-hour `cache-control`. A cover
 * replaced at the same key stayed the old picture in the teacher's own
 * browser for up to an hour after a successful upload — indistinguishable,
 * from where they sit, from an upload that did nothing.
 *
 * The caller deletes the previous object once the new URL is safely
 * persisted; see `removePublicObject`.
 */
async function uploadToPublicBucket(
  bucket: string,
  path: string,
  file: File,
): Promise<string> {
  await putPublicObject(bucket, path, file)
  return getPublicUrl(bucket, path)
}

/**
 * How a public object may be cached: for a year, by anyone, unchanged.
 *
 * True by construction — every public key is fresh (`cover-<hex>`,
 * `avatar-<hex>`, `content-images/<ms>-<hex>`) and never written twice, so
 * a cached copy can never be stale. Storage serves whatever `cache-control`
 * the object was stored with, and objects uploaded the old way came back
 * `no-cache`: every view of every cover went through to Storage and no CDN
 * in between kept a copy. `s-maxage` is for the edge in front of `/img/`:
 * Vercel keeps an external rewrite's response only when the origin allows
 * a shared cache to. Objects uploaded before this keep their old
 * `no-cache`; rewriting them was judged not worth it (2026-10-17).
 */
export const PUBLIC_OBJECT_CACHE_CONTROL = "public, max-age=31536000, s-maxage=86400, immutable"

/**
 * Upload the bytes rather than the `File`.
 *
 * storage-js sends a `File` as multipart, and on that path Storage builds
 * the header itself — `max-age=<cacheControl>`, or `no-cache` when it does
 * not find the field, which is what production objects carry. A plain body
 * is stored with the `cache-control` header exactly as sent (Storage's
 * `uploader.ts`), so the value above is what the object answers with.
 * The content type is then ours to state; `withBucketContentType` has
 * already settled it for the bucket.
 */
async function putPublicObject(bucket: string, path: string, file: File): Promise<void> {
  const { error } = await supabase.storage.from(bucket).upload(path, await file.arrayBuffer(), {
    contentType: file.type || "application/octet-stream",
    headers: { "cache-control": PUBLIC_OBJECT_CACHE_CONTROL },
  })
  if (error) throw error
}

/**
 * Split a URL this module produced back into its bucket and object key.
 * Accepts both the proxied `/img/<bucket>/<path>` form we store and the
 * raw Supabase public URL, since older rows hold the latter. Anything
 * else — an external image, a blob:, a malformed row — returns `null`
 * and is left alone.
 */
export function parsePublicObjectUrl(
  url: string | null | undefined,
): { bucket: string; path: string } | null {
  if (!url) return null
  let pathname: string
  try {
    pathname = new URL(url, window.location.origin).pathname
  } catch {
    return null
  }
  const RAW_PREFIX = "/storage/v1/object/public/"
  const rest = pathname.startsWith("/img/")
    ? pathname.slice("/img/".length)
    : pathname.startsWith(RAW_PREFIX)
      ? pathname.slice(RAW_PREFIX.length)
      : null
  if (!rest) return null
  const slash = rest.indexOf("/")
  if (slash <= 0 || slash === rest.length - 1) return null
  return {
    bucket: decodeURIComponent(rest.slice(0, slash)),
    path: decodeURIComponent(rest.slice(slash + 1)),
  }
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

/** A Storage refusal, in the shape `describeUploadError` reads
 *  (`StorageApiError` carries `statusCode` as a string). */
interface StorageRefusal {
  statusCode: string
  error: string
  message: string
}

/**
 * Upload a plain body to a bucket and report progress along the way.
 *
 * storage-js uploads through `fetch`, which cannot say how much has gone;
 * a 30 MB voice memo on 3G is minutes of nothing on the screen, and a
 * student who sees nothing presses the button again. `XMLHttpRequest`
 * reports `upload.progress`, so this one path uses it, against the same
 * endpoint storage-js posts to (`POST /storage/v1/object/<bucket>/<key>`),
 * with the session's own token: the bucket's RLS decides, as everywhere.
 *
 * `onProgress` gets 0..1. A refusal rejects with Storage's own JSON body
 * (`{statusCode, error, message}`), which `describeUploadError` already
 * speaks; a request that never got an answer rejects with a `TypeError`,
 * which it reads as the network.
 */
async function putWithProgress(
  bucket: string,
  path: string,
  file: File,
  onProgress?: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) {
    throw { statusCode: "401", error: "Unauthorized", message: "no session" } satisfies StorageRefusal
  }
  const key = path.split("/").map(encodeURIComponent).join("/")
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("POST", `${SUPABASE_URL}/storage/v1/object/${bucket}/${key}`)
    xhr.setRequestHeader("Authorization", `Bearer ${token}`)
    xhr.setRequestHeader("apikey", SUPABASE_ANON_KEY)
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream")
    xhr.setRequestHeader("x-upsert", "false")
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && e.total > 0) onProgress?.(Math.min(1, e.loaded / e.total))
    }
    xhr.onerror = () => reject(new TypeError("Failed to fetch"))
    xhr.onabort = () => reject(new TypeError("Failed to fetch"))
    // The student took the file back while it was still going up.
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"))
      return
    }
    signal?.addEventListener("abort", () => xhr.abort(), { once: true })
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(1)
        resolve()
        return
      }
      let body: Partial<StorageRefusal> = {}
      try {
        body = JSON.parse(xhr.responseText) as Partial<StorageRefusal>
      } catch {
        // A proxy's HTML page, or nothing at all.
      }
      reject({
        statusCode: String(body.statusCode ?? xhr.status),
        error: body.error ?? "StorageError",
        message: body.message ?? xhr.statusText,
      } satisfies StorageRefusal)
    }
    xhr.send(file)
  })
}

export const storageService = {
  async uploadAvatar(userId: string, file: File): Promise<string> {
    refuseWhileViewingAs()
    const path = `${userId}/avatar-${crypto.randomUUID().slice(0, 8)}.${fileExtension(file.name)}`
    return uploadToPublicBucket(AVATARS_BUCKET, path, file)
  },

  async uploadCourseImage(courseId: string, file: File): Promise<string> {
    refuseWhileViewingAs()
    const path = `${courseId}/cover-${crypto.randomUUID().slice(0, 8)}.${fileExtension(file.name)}`
    return uploadToPublicBucket(COURSE_ASSETS_BUCKET, path, withBucketContentType(file, COURSE_ASSETS))
  },

  /**
   * An organization's logo: the avatar recipe with the organization's id
   * as the folder. The bucket's RLS admits the folder to the organization's
   * director and to platform staff, and `PATCH /organizations/{id}/profile`
   * accepts a `logo_url` only of this exact shape.
   */
  async uploadOrganizationLogo(organizationId: string, file: File): Promise<string> {
    refuseWhileViewingAs()
    // The extension comes from the type, not from the name: a key is ASCII
    // or Storage refuses it, and "лого.пнг" is a PNG all the same.
    const typed = withBucketContentType(file, ORGANIZATION_LOGOS)
    const path = `${organizationId}/logo-${crypto.randomUUID().slice(0, 8)}.${LOGO_EXTENSION[typed.type] ?? "jpg"}`
    return uploadToPublicBucket(ORGANIZATION_LOGOS_BUCKET, path, typed)
  },

  /**
   * Delete an object this module uploaded, addressed by the public URL
   * that was stored for it. Best-effort by design: the caller runs this
   * *after* the replacement URL is persisted, so a failure here leaves an
   * orphaned file and nothing else. Never let it surface as an error on
   * an upload the user watched succeed.
   */
  async removePublicObject(url: string | null | undefined): Promise<void> {
    refuseWhileViewingAs()
    const target = parsePublicObjectUrl(url)
    if (!target) return
    await supabase.storage.from(target.bucket).remove([target.path])
  },

  /**
   * Upload a course material file into the private `course-materials` bucket.
   * Returns nothing — every caller refreshes its own list afterwards and
   * signs URLs on demand via `getSignedMaterialUrl`. Previously this minted
   * a 1-year signed URL as a workaround for short TTLs; that bandaid is
   * gone now that chapter file blocks re-sign on click too.
   */
  async uploadCourseMaterial(courseId: string, file: File): Promise<void> {
    refuseWhileViewingAs()
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
        // The object is stored as ``<ms timestamp>-<name>`` (see
        // ``uploadCourseMaterial``), and students were shown
        // ``1789274605316-Lesson_1.pdf``. The path keeps the stamp; only
        // the name a person reads drops it.
        name: f.name.replace(/^\d{13}-/, ""),
        path: `${courseId}/${f.name}`,
        size: f.metadata?.size as number | undefined,
        created: f.created_at,
      }))
  },

  async getSignedMaterialUrl(path: string): Promise<string> {
    return createSignedDownloadUrl(COURSE_MATERIALS_BUCKET, path)
  },

  async deleteCourseMaterial(path: string): Promise<void> {
    refuseWhileViewingAs()
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
    refuseWhileViewingAs()
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

  /**
   * A student's file for an assignment, into the private `submissions`
   * bucket. The key is the one shape the bucket's RLS and the API accept:
   * `<course>/<assignment>/<student>/<ms>-<safe_name>` -- the student's own
   * folder is the third segment, and `POST /assignments/{id}/submit`
   * refuses a `file.path` outside it. The caller hands the returned
   * `{ bucket, path, name }` in with the work; the teacher signs a URL on
   * click (`getSignedSubmissionFileUrl`).
   */
  async uploadSubmissionFile(
    courseId: string,
    assignmentId: string,
    studentId: string,
    file: File,
    onProgress?: (fraction: number) => void,
    signal?: AbortSignal,
  ): Promise<UploadedBlockFile> {
    refuseWhileViewingAs()
    const path = `${courseId}/${assignmentId}/${studentId}/${Date.now()}-${sanitizeFileName(file.name)}`
    await putWithProgress(SUBMISSIONS_BUCKET, path, withBucketContentType(file, SUBMISSIONS), onProgress, signal)
    return { bucket: SUBMISSIONS_BUCKET, path, name: file.name }
  },

  /** The «remove» cross between choosing a file and handing it in. The
   *  bucket refuses this once a submission names the key; best-effort. */
  async removeSubmissionFile(path: string): Promise<void> {
    refuseWhileViewingAs()
    await supabase.storage.from(SUBMISSIONS_BUCKET).remove([path])
  },

  /** Mint a short-lived signed URL for a student's handed-in file. */
  async getSignedSubmissionFileUrl(bucket: string, path: string): Promise<string> {
    return createSignedDownloadUrl(bucket, path)
  },

  async uploadContentImage(file: File): Promise<string> {
    refuseWhileViewingAs()
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

    return uploadToPublicBucket(COURSE_ASSETS_BUCKET, path, withBucketContentType(file, COURSE_ASSETS))
  },
}
