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

export function makeLoginSchema() {
  return z.object({
    email: z.string().email(t("authRegister.errors.emailInvalid")),
    // Deliberately only "not empty". Signing in does not create a password,
    // and holding an existing one to today's minimum would lock out every
    // account made before `password_min_length` was raised to 12 — a rule
    // about new passwords, enforced against people who already have one.
    password: z.string().min(1, t("auth.errors.passwordRequired")),
  })
}

export function makeRegisterSchema() {
  // Self-service signup is student-only — role isn't part of the form
  // since 2026-05-31. Teacher promotion is admin-only.
  return z
    .object({
      full_name: z.string().min(2, t("authRegister.errors.fullNameTooShort")),
      email: z.string().email(t("authRegister.errors.emailInvalid")),
      password: z.string().min(PASSWORD_MIN_LENGTH, tooShort()),
      confirmPassword: z.string(),
    })
    .refine((data) => data.password === data.confirmPassword, {
      message: t("authRegister.errors.passwordsDoNotMatch"),
      path: ["confirmPassword"],
    })
}

// Same shape as makeRegisterSchema minus `email` -- the accept-invite
// page fixes the email to whatever the invite was issued to, so there's
// no editable email field to validate.
export function makeAcceptInviteSchema() {
  return z
    .object({
      full_name: z.string().min(2, t("authRegister.errors.fullNameTooShort")),
      password: z.string().min(PASSWORD_MIN_LENGTH, tooShort()),
      confirmPassword: z.string(),
    })
    .refine((data) => data.password === data.confirmPassword, {
      message: t("authRegister.errors.passwordsDoNotMatch"),
      path: ["confirmPassword"],
    })
}

// Static snapshots removed — every caller now invokes the factory
// inside the submit handler so error messages match the active
// locale (see ``Login.tsx`` / ``useRegister.ts`` / ``ResetPassword.tsx``).

export type LoginFormData = z.infer<ReturnType<typeof makeLoginSchema>>
