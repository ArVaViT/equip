/**
 * The password rules a person is actually held to — in one place, because
 * the form and the server used to disagree.
 *
 * Every zod schema in the app asked for six characters. Supabase Auth is
 * configured `password_min_length = 12` with `password_hibp_enabled = true`,
 * so the real rules were a twelve-character minimum plus a check against
 * Have I Been Pwned — neither of which any screen mentioned. A person met
 * them only as a refusal after submit: three in a row on 2026-08-30, in the
 * auth logs, over three minutes, before that account was finally created.
 *
 * `PASSWORD_MIN_LENGTH` must equal the project's `password_min_length`.
 * The two cannot be wired together at runtime — that setting lives in the
 * Supabase project config, not in this repo — so it is a constant here and a
 * line in `docs/adr/` if it ever moves.
 */
export const PASSWORD_MIN_LENGTH = 12

/**
 * A rule the browser can decide for itself while somebody types.
 *
 * "Not found in a known breach" is deliberately absent. That check runs on
 * Supabase's side against Have I Been Pwned, and a browser cannot answer it
 * without sending the password somewhere it has no business going. Awarding
 * a tick this code cannot honestly earn would be worse than saying plainly
 * that the check happens on submit — which is what the `leakedNote` string
 * under `auth.password` does.
 */
export type PasswordRuleId = "length" | "match"

export interface PasswordRuleState {
  id: PasswordRuleId
  met: boolean
}

/**
 * The live state of every locally checkable rule.
 *
 * `match` stays false for an empty password on purpose: two empty fields are
 * equal, and ticking "the passwords match" before either has been typed
 * reads as progress the person has not made.
 */
export function checkPassword(password: string, confirmPassword: string): PasswordRuleState[] {
  return [
    { id: "length", met: password.length >= PASSWORD_MIN_LENGTH },
    { id: "match", met: password.length > 0 && password === confirmPassword },
  ]
}

export function passwordMeetsLocalRules(password: string, confirmPassword: string): boolean {
  return checkPassword(password, confirmPassword).every((rule) => rule.met)
}

/**
 * Alphabet for generated passwords: no `l`/`I`/`1`/`O`/`0`, which are the
 * characters people mistype when they read a password off one screen and
 * key it into another. Symbols are left out for the same reason — the
 * project requires none (`password_required_characters` is empty), and a
 * password that survives being retyped by hand is worth more here than four
 * extra bits of entropy.
 */
const GENERATED_ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

/** 20 characters over a 56-character alphabet — about 116 bits. */
const GENERATED_LENGTH = 20

/**
 * A password nobody has to invent.
 *
 * Uses `crypto.getRandomValues` with rejection sampling rather than `%` on a
 * raw draw: 2^32 is not a multiple of 56, so folding the tail back in with a
 * modulo would make the first few letters of the alphabet very slightly more
 * likely than the rest. The bias is tiny and the fix is three lines, so
 * there is no reason to ship the biased version.
 */
export function generatePassword(length: number = GENERATED_LENGTH): string {
  const alphabet = GENERATED_ALPHABET
  const limit = Math.floor(0x100000000 / alphabet.length) * alphabet.length
  const draw = new Uint32Array(1)
  let out = ""
  while (out.length < length) {
    crypto.getRandomValues(draw)
    const value = draw[0]
    // `noUncheckedIndexedAccess` is on, and it is right to insist: a caller
    // could hand us a zero-length draw. Skipping is the safe branch.
    if (value === undefined || value >= limit) continue
    out += alphabet.charAt(value % alphabet.length)
  }
  return out
}
