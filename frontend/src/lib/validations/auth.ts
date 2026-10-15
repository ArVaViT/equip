import { z } from "zod"
import i18n from "@/i18n/config"
import { PASSWORD_MIN_LENGTH } from "@/lib/passwordPolicy"

/**
 * Auth validation schemas.
 *
 * Error messages resolve via i18next at schema-construction time, so
 * every caller MUST invoke the ``make…Schema()`` factory inside its
 * submit handler — never cache the returned schema at module scope.
 * Caching would snapshot the bootstrap-locale strings and leave error
 * messages stuck in the wrong language after a locale switch.
 */
const t = (key: string, options?: Record<string, unknown>) => i18n.t(key, options)

/** The length message carries the number, so the reader is told the actual rule. */
const tooShort = () => t("authRegister.errors.passwordTooShort", { count: PASSWORD_MIN_LENGTH })

/**
 * An address as people actually type and paste it: a trailing space from
 * autocomplete or a copied line is not part of it, and GoTrue would refuse
 * the whole address for it.
 */
const email = () => z.string().trim().email(t("authRegister.errors.emailInvalid"))

const newPassword = () => z.string().min(PASSWORD_MIN_LENGTH, tooShort())

export function makeLoginSchema() {
  return z.object({
    email: email(),
    // Deliberately only "not empty". Signing in does not create a password,
    // and holding an existing one to today's minimum would lock out every
    // account made before `password_min_length` was raised to 12 — a rule
    // about new passwords, enforced against people who already have one.
    password: z.string().min(1, t("auth.errors.passwordRequired")),
  })
}

/** Just an address — for the screens that send a link to one. */
export function makeEmailSchema() {
  return z.object({ email: email() })
}

export function makeRegisterSchema() {
  // Self-service signup is student-only — role isn't part of the form
  // since 2026-05-31. Teacher promotion is admin-only.
  return z.object({
    full_name: z.string().trim().min(2, t("authRegister.errors.fullNameTooShort")),
    email: email(),
    password: newPassword(),
  })
}

// The register form minus `email` -- the accept-invite page fixes the
// address to the one the invitation was sent to.
export function makeAcceptInviteSchema() {
  return z.object({
    full_name: z.string().trim().min(2, t("authRegister.errors.fullNameTooShort")),
    password: newPassword(),
  })
}

export function makeNewPasswordSchema() {
  return z.object({ password: newPassword() })
}

// Static snapshots removed — every caller now invokes the factory
// inside the submit handler so error messages match the active
// locale (see ``Login.tsx`` / ``useRegister.ts`` / ``ResetPassword.tsx``).

export type LoginFormData = z.infer<ReturnType<typeof makeLoginSchema>>
