/** Put a saved comment after what is already written, on its own line — never in place of it. */
export function appendComment(current: string, comment: string): string {
  const head = current.trimEnd()
  return head ? `${head}\n${comment}` : comment
}
