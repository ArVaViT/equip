/**
 * Whether a card's title only says again what the page's title says.
 *
 * «Эссе: что изменилось в Пятидесятницу» already says «Что изменилось в
 * Пятидесятницу», and «Проверьте себя: Пятидесятница» says «Пятидесятница».
 * Case and punctuation aside; whole words only, so «Пасха» is not repeated
 * by «Пасхальные гимны».
 */
export function repeatsTitle(pageTitle: string, title: string): boolean {
  const norm = (s: string) => ` ${s.toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim()} `
  const inner = norm(title)
  return inner.trim().length > 0 && norm(pageTitle).includes(inner)
}
