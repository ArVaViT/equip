import { useCallback, useState } from "react"
import { useAuth } from "@/context/useAuth"
import { makeRegisterSchema } from "@/lib/validations/auth"
import i18n, { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"
import { authErrorMessage, isDuplicateEmail } from "@/lib/authError"
import { generatePassword } from "@/lib/passwordPolicy"

export type FormState = {
  full_name: string
  email: string
  password: string
  confirmPassword: string
}

const EMPTY_FORM: FormState = {
  full_name: "",
  email: "",
  password: "",
  confirmPassword: "",
}

/**
 * Registration form state machine.
 *
 * Exposes the mutable form + per-field validation errors, the three
 * terminal states (server error, duplicate-email, success), and the two
 * async handlers (email/password submit and Google OAuth). The view just
 * renders whichever state is active; nothing else lives in the page.
 */
export function useRegister() {
  const { register, signInWithGoogle } = useAuth()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({})
  const [serverError, setServerError] = useState("")
  const [duplicateEmail, setDuplicateEmail] = useState(false)
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [passwordGenerated, setPasswordGenerated] = useState(false)

  const handleChange = useCallback(
    (field: keyof FormState, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }))
      setErrors((prev) => ({ ...prev, [field]: undefined }))
      // Typing over a generated password makes the "save it" note stale.
      if (field === "password" || field === "confirmPassword") setPasswordGenerated(false)
    },
    [],
  )

  const toggleShowPassword = useCallback(() => {
    setShowPassword((prev) => !prev)
  }, [])

  /**
   * Fill both password fields with something that satisfies the rules.
   *
   * Reveals the password as a deliberate part of the action: a value nobody
   * chose and nobody can see is a value nobody can write down, and the next
   * screen after this one asks for it again. `passwordGenerated` drives the
   * "save this in your password manager" line.
   */
  const handleGeneratePassword = useCallback(() => {
    const generated = generatePassword()
    setForm((prev) => ({ ...prev, password: generated, confirmPassword: generated }))
    setErrors((prev) => ({ ...prev, password: undefined, confirmPassword: undefined }))
    setShowPassword(true)
    setPasswordGenerated(true)
  }, [])

  const handleSubmit = useCallback(async () => {
    setServerError("")

    const result = makeRegisterSchema().safeParse(form)
    if (!result.success) {
      const fieldErrors: Partial<Record<string, string>> = {}
      for (const issue of result.error.issues) {
        const key = String(issue.path[0])
        if (!fieldErrors[key]) fieldErrors[key] = issue.message
      }
      setErrors(fieldErrors)
      return
    }

    setLoading(true)
    try {
      // Source the new user's ``preferred_locale`` from the language
      // the registration form was rendered in — that's whatever
      // i18next resolved (browser language for first-time visitors,
      // localStorage for returning ones). The trigger whitelists this
      // value against the same supported set as the DB CHECK, so a
      // surprise locale gracefully falls back to the column default.
      const preferredLocale = isSupportedLocale(i18n.resolvedLanguage)
        ? i18n.resolvedLanguage
        : DEFAULT_LOCALE
      await register(
        result.data.email,
        result.data.password,
        result.data.full_name,
        preferredLocale,
      )
      setSuccess(true)
    } catch (err) {
      if (isDuplicateEmail(err)) {
        // Its own panel, not a red sentence — the reader almost certainly
        // has an account and wants the sign-in link, not an error.
        setDuplicateEmail(true)
      } else {
        // The server's `message` is always there, so the fallback after the
        // old `||` never ran: a German creating an account was told
        // "Password should be at least 6 characters" in English on a German
        // form. Translated now; the raw text goes to the dev console.
        setServerError(authErrorMessage(err, "auth.errors.registrationFailed"))
      }
    } finally {
      setLoading(false)
    }
  }, [form, register])

  const handleGoogleSignUp = useCallback(async () => {
    setGoogleLoading(true)
    try {
      await signInWithGoogle()
    } catch (err) {
      setServerError(authErrorMessage(err, "auth.errors.googleSignUpFailed"))
    } finally {
      setGoogleLoading(false)
    }
  }, [signInWithGoogle])

  return {
    form,
    errors,
    serverError,
    duplicateEmail,
    success,
    loading,
    googleLoading,
    showPassword,
    passwordGenerated,
    toggleShowPassword,
    handleGeneratePassword,
    handleChange,
    handleSubmit,
    handleGoogleSignUp,
  }
}
