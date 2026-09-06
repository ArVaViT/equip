/**
 * A 422 in the reader's language, pointing at the field.
 *
 * FastAPI answers a body that fails validation with a list of
 * ``{loc, msg, type, ctx}``. The ``msg`` is English written by pydantic
 * ("Input should be less than or equal to 100") and used to be joined
 * with semicolons into the toast, so a teacher who typed 150 points read
 * an English sentence that did not say which question it meant.
 *
 * ``loc`` says where (``["body", "questions", 1, "points"]``), ``type``
 * says what kind of wrong (``less_than_equal``), and ``ctx`` carries the
 * number (``{le: 100}``). All three are stable identifiers, so the
 * sentence can be ours: «Вопрос 2, баллы: не больше 100». The backend's
 * own validators raise custom types (``quiz_no_correct_option``) for the
 * same reason — the type is translated, the msg is for a log.
 */

import i18n from "@/i18n/config"

export interface ValidationEntry {
  loc?: unknown
  type?: unknown
  ctx?: unknown
}

export function isValidationList(value: unknown): value is ValidationEntry[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((entry) => entry && typeof entry === "object" && "loc" in entry && "type" in entry)
  )
}

/** Fields the catalogue has a name for; anything else is shown as its key. */
const FIELD_KEYS = new Set([
  "title",
  "description",
  "passing_score",
  "max_attempts",
  "quiz_type",
  "questions",
  "question_text",
  "question_type",
  "points",
  "min_words",
  "options",
  "option_text",
  "is_correct",
  "order_index",
])

/** Error types the catalogue has a sentence for. */
const TYPE_KEYS = new Set([
  "less_than_equal",
  "less_than",
  "greater_than_equal",
  "greater_than",
  "string_too_short",
  "string_too_long",
  "too_short",
  "too_long",
  "missing",
  "extra_forbidden",
  "int_parsing",
  "int_type",
  "int_from_float",
  "string_type",
  "bool_type",
  "literal_error",
  "quiz_question_blank",
  "quiz_option_blank",
  "quiz_too_few_options",
  "quiz_no_correct_option",
  "quiz_many_correct_options",
  "quiz_options_not_allowed",
])

/**
 * «Вопрос 2, вариант 3, текст варианта» — the path to the field, in words.
 *
 * Indices in ``loc`` count from zero and follow the list they index;
 * the reader counts questions from one, so ``["questions", 1]`` is the
 * second question. The leading ``"body"`` is transport, not location.
 */
function describeLocation(loc: unknown): string {
  if (!Array.isArray(loc)) return ""
  const parts: string[] = []
  const path = loc.filter((segment) => segment !== "body")
  for (let i = 0; i < path.length; i += 1) {
    const segment = path[i]
    const next = path[i + 1]
    if (typeof segment === "string" && typeof next === "number") {
      const whereKey = `errors.where.${segment}`
      parts.push(i18n.exists(whereKey) ? i18n.t(whereKey, { n: next + 1 }) : `${segment} ${next + 1}`)
      i += 1
      continue
    }
    if (typeof segment === "string") {
      parts.push(FIELD_KEYS.has(segment) ? i18n.t(`errors.fields.${segment}`) : segment)
    }
  }
  return parts.join(", ")
}

function describeType(type: unknown, ctx: unknown): string {
  const key = typeof type === "string" && TYPE_KEYS.has(type) ? `errors.validation.${type}` : "errors.validation.invalid"
  const values = ctx && typeof ctx === "object" ? (ctx as Record<string, unknown>) : {}
  return i18n.t(key, values)
}

/**
 * One sentence per failed field, joined for a toast. The caller decides
 * whether the list is a validation list — see ``isValidationList``.
 */
export function describeValidationErrors(entries: ValidationEntry[]): string {
  const sentences = entries.map((entry) => {
    const where = describeLocation(locationFor(entry))
    const what = describeType(entry.type, entry.ctx)
    return where ? `${where}: ${what}` : what
  })
  return sentences.join("; ")
}

/**
 * Our own validator types already say which field they mean («введите
 * текст варианта»), so the field's name is dropped from the path and
 * only the question and option numbers remain. Pydantic's generic types
 * («не больше 100») need the field to make sense.
 */
function locationFor(entry: ValidationEntry): unknown {
  const { loc, type } = entry
  if (typeof type === "string" && type.startsWith("quiz_") && Array.isArray(loc)) {
    const last = loc[loc.length - 1]
    if (typeof last === "string" && FIELD_KEYS.has(last)) return loc.slice(0, -1)
  }
  return loc
}
