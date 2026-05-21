import { supabase } from "@/lib/supabase"

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
 * Strip path-illegal characters and collapse whitespace, then cap the
 * result without losing the file extension. The previous version sliced
 * to 100 chars *after* the special-char replacement, which silently
 * dropped the trailing ``.pdf`` / ``.png`` on any name longer than 100
 * chars and produced extensionless object keys (broken MIME sniffing /
 * download UX). Truncate the stem, then re-append the extension.
 *
 * Exported only so the unit test can exercise the boundary case
 * directly — runtime callers should use the upload functions below.
 */
export function sanitizeFileName(name: string): string {
  const cleaned = name.replace(/[/\\:*?"<>|]/g, "_").replace(/\s+/g, "_")
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
    return uploadToPublicBucket(COURSE_ASSETS_BUCKET, path, file)
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
      .upload(path, file)

    if (error) throw error
  },

  async listCourseMaterials(courseId: string): Promise<{ name: string; path: string; size: number | undefined; created: string | null }[]> {
    const { data, error } = await supabase.storage
      .from(COURSE_MATERIALS_BUCKET)
      .list(courseId, { sortBy: { column: "created_at", order: "desc" } })

    if (error) throw error
    return (data ?? []).map((f) => ({
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
  async uploadBlockFile(chapterId: string, file: File): Promise<UploadedBlockFile> {
    const timestamp = Date.now()
    const safeName = sanitizeFileName(file.name)
    const path = `${chapterId}/${timestamp}-${safeName}`

    const { error } = await supabase.storage
      .from(COURSE_MATERIALS_BUCKET)
      .upload(path, file)

    if (error) throw error

    return { bucket: COURSE_MATERIALS_BUCKET, path, name: file.name }
  },

  /** Mint a short-lived signed URL for a block-attached file. */
  async getSignedBlockFileUrl(bucket: string, path: string): Promise<string> {
    return createSignedDownloadUrl(bucket, path)
  },

  async uploadContentImage(file: File): Promise<string> {
    const ext = fileExtension(file.name)
    const random = Math.random().toString(36).slice(2, 10)
    const path = `content-images/${Date.now()}-${random}.${ext}`

    // Content images use upsert: false so the random suffix prevents
    // overwriting an existing path; `uploadToPublicBucket` would upsert.
    const { error } = await supabase.storage.from(COURSE_ASSETS_BUCKET).upload(path, file)
    if (error) throw error
    return getPublicUrl(COURSE_ASSETS_BUCKET, path)
  },
}
