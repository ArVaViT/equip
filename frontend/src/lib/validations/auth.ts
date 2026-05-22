import { z } from "zod"
import i18n from "@/i18n/config"

/**
 * Auth validation schemas.
 *
 * Error messages resolve via i18next at schema-construction time, so
 * every caller MUST invoke the ``make…Schema()`` factory inside its
 * submit handler — never cache the returned schema at module scope.
 * Caching would snapshot the bootstrap-locale strings and leave error
 * messages stuck in the wrong language after a locale switch.
 */
const t = (key: string) => i18n.t(key)

export function makeLoginSchema() {
  return z.object({
    email: z.string().email(t("authRegister.errors.emailInvalid")),
    password: z.string().min(6, t("authRegister.errors.passwordTooShort")),
  })
}

export function makeRegisterSchema() {
  return z
    .object({
      full_name: z.string().min(2, t("authRegister.errors.fullNameTooShort")),
      email: z.string().email(t("authRegister.errors.emailInvalid")),
      password: z.string().min(6, t("authRegister.errors.passwordTooShort")),
      confirmPassword: z.string(),
      role: z.enum(["teacher", "student"], {
        message: t("authRegister.errors.roleRequired"),
      }),
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
