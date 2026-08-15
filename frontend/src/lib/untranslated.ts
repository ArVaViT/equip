import type { TFunction } from "i18next"

/**
 * What to show where a text has no version in the reader's language.
 *
 * The backend used to hand back the teacher's original in that case, so
 * every surface could assume a string was always there. It does not any
 * more: nobody is served a language they did not choose, and an empty
 * title arrives instead.
 *
 * Empty is honest but mute — it looks like a bug, or like the teacher
 * forgot to name the chapter. This says the true thing: the material
 * exists, it is simply not in your language yet.
 *
 * Narrow by design. Under the publication gate a course cannot enter the
 * catalog until every language has it, so a reader meets this in the gap
 * between a teacher posting something and the worker translating it.
 */
export function orNotTranslated(t: TFunction, text: string | null | undefined): string {
  const trimmed = (text ?? "").trim()
  return trimmed === "" ? t("common.notTranslatedYet") : trimmed
}
