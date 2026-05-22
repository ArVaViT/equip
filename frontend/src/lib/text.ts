/**
 * Word count for free-form text — splits on any whitespace, ignores
 * empty fragments, returns 0 for null/blank.
 *
 * Used by the quiz taker (essay min-word gate), the quiz submissions
 * review (teacher's word-count badge), and the essay answer textarea
 * (live counter under the input). Same definition across all three so
 * a student's "you're at 47 words" matches the teacher's "47 / 100 words"
 * exactly -- previously each callsite had its own copy with subtle
 * differences (trim-or-not, filter-or-not).
 */
export function countWords(text: string | null | undefined): number {
  if (!text) return 0
  const trimmed = text.trim()
  if (!trimmed) return 0
  return trimmed.split(/\s+/).filter(Boolean).length
}
