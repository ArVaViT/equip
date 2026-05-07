import { z } from "zod"

import { CHAPTER_TYPES } from "@/lib/chapterTypes"
import i18n from "@/i18n/config"

/**
 * Frontend validation schemas. Ranges intentionally mirror the Pydantic
 * schemas in ``backend/app/schemas/course.py`` so invalid input fails fast
 * client-side before we hit the server.
 *
 * User-facing message keys are resolved via i18next; the static schema
 * exports snapshot the bootstrap language at module-load. Components that
 * surface these errors to the user (course/module editors, profile page)
 * should call the matching `make*Schema()` factory inside their submit
 * handler so the error string matches the active UI language.
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
    image_url: optionalString(2048),
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

export const courseSchema = makeCourseSchema()
export const moduleSchema = makeModuleSchema()
export const chapterSchema = makeChapterSchema()
export const profileSchema = makeProfileSchema()

export type CourseFormData = z.infer<ReturnType<typeof makeCourseSchema>>
