/**
 * The letters that stand in for an organization's logo until it has one.
 *
 * The first letter of the name was the whole answer, and for most names it
 * is a poor one: half the organizations here are called «Церковь …»,
 * «Школа …» or «Миссия …», so half the tiles said «Ц», «Ш» or «М» — the
 * kind of word, not the name. The name is what follows: «Церковь «Слово
 * Жизни»» is «СЖ», the way its own members would abbreviate it.
 *
 * Quotes of every national habit are stripped before the words are read,
 * so an opening «» or „“ never becomes the initial.
 */

//: The words that say what kind of organization it is, not which one.
//: Lower-cased; compared after the quotes are gone. ru, uk, en, de —
//: the four languages of the interface.
const GENERIC = new Set([
  "церковь", "школа", "колледж", "миссия", "служение", "институт", "семинария",
  "церква", "коледж", "місія", "служіння", "інститут", "семінарія",
  "church", "school", "college", "mission", "ministry", "institute", "seminary",
  "kirche", "gemeinde", "schule", "mission", "institut", "seminar",
])

const QUOTES = /[«»„“”"'‘’‹›]/g

export function organizationInitials(name: string): string {
  const words = name.replace(QUOTES, " ").split(/\s+/).filter(Boolean)
  if (words.length === 0) return ""
  let rest = words
  while (rest.length > 1 && GENERIC.has(rest[0]!.toLowerCase())) rest = rest.slice(1)
  // A name of one word is one letter («UCOAT» → «U»); two or more give two,
  // which is as many as a tile can carry at this size.
  return rest
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join("")
}
