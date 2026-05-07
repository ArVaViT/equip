import { z } from "zod"
import i18n from "@/i18n/config"

/**
 * Auth validation schemas.
 *
 * Error messages are translated via i18next at schema-construction time and
 * also re-resolved each time a builder is invoked, so the messages match
 * the active UI language whenever a form actually validates.
 *
 * Static `loginSchema` / `registerSchema` exports are kept for backwards
 * compatibility — they snapshot the bootstrap language. Components that
 * need the current locale (i.e. anything user-facing) should call
 * `makeLoginSchema()` / `makeRegisterSchema()` inside their submit handler.
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

export const loginSchema = makeLoginSchema()
export const registerSchema = makeRegisterSchema()

export type LoginFormData = z.infer<ReturnType<typeof makeLoginSchema>>
