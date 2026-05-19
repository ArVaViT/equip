import { z } from "zod"

import { CHAPTER_TYPES } from "@/lib/chapterTypes"
import i18n from "@/i18n/config"

/**
 * Frontend validation schemas. Ranges intentionally mirror the Pydantic
 * schemas in ``backend/app/schemas/course.py`` so invalid input fails fast
 * client-side before we hit the server.
 *
 * Error messages resolve via i18next at schema-construction time, so
 * every caller MUST invoke the ``make…Schema()`` factory inside its
 * submit handler — never cache the returned schema at module scope.
 * Caching snapshots the bootstrap-locale strings and leaves messages
 * stuck in the wrong language after a locale switch.
 */

const t = (key: string) => i18n.t(key)

const optionalString = (max: number) =>
  z
    .string()
    .max(max)
    .optional()
    .or(z.literal(""))

export function makeCourseSchema() {
  return z.object({
    title: z
      .string()
      .trim()
      .min(1, t("validation.titleRequired"))
      .max(300, t("validation.titleTooLong")),
    description: optionalString(10_000),
  })
}

export function makeModuleSchema() {
  return z.object({
    title: z
      .string()
      .trim()
      .min(1, t("validation.titleRequired"))
      .max(300, t("validation.titleTooLong")),
    description: optionalString(5_000),
    order_index: z.number().int().min(0).default(0),
    due_date: z.string().datetime().nullable().optional(),
  })
}

export function makeChapterSchema() {
  return z.object({
    title: z
      .string()
      .trim()
      .min(1, t("validation.titleRequired"))
      .max(300, t("validation.titleTooLong")),
    order_index: z.number().int().min(0).default(0),
    chapter_type: z.enum(CHAPTER_TYPES).default("reading"),
    requires_completion: z.boolean().default(false),
    is_locked: z.boolean().default(false),
  })
}

export function makeProfileSchema() {
  return z.object({
    full_name: z
      .string()
      .trim()
      .min(2, t("validation.nameTooShort"))
      .max(100),
  })
}

// Static schema exports were ``= make…Schema()`` snapshots that froze
// error messages at bootstrap-locale. Every callsite has been converted
// to invoke the ``make…Schema()`` factory inside the submit handler so
// validation messages update with the active locale; the snapshots are
// gone now. Re-add them only if a non-user-facing caller appears (rare).

export type CourseFormData = z.infer<ReturnType<typeof makeCourseSchema>>
