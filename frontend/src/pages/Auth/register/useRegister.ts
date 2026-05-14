import { useCallback, useState } from "react"
import { useAuth } from "@/context/useAuth"
import { makeRegisterSchema } from "@/lib/validations/auth"
import i18n, { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"

export type FormState = {
  full_name: string
  email: string
  password: string
  confirmPassword: string
  role: "teacher" | "student"
}

const EMPTY_FORM: FormState = {
  full_name: "",
  email: "",
  password: "",
  confirmPassword: "",
  role: "student",
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

  const handleChange = useCallback(
    (field: keyof FormState, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }))
      setErrors((prev) => ({ ...prev, [field]: undefined }))
    },
    [],
  )

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
        result.data.role,
        preferredLocale,
      )
      setSuccess(true)
    } catch (err: unknown) {
      const supaErr = err as { message?: string }
      if (supaErr.message === "DUPLICATE_EMAIL") {
        setDuplicateEmail(true)
      } else {
        setServerError(supaErr.message || i18n.t("auth.errors.registrationFailed"))
      }
    } finally {
      setLoading(false)
    }
  }, [form, register])

  const handleGoogleSignUp = useCallback(async () => {
    setGoogleLoading(true)
    try {
      await signInWithGoogle()
    } catch (err: unknown) {
      const supaErr = err as { message?: string }
      setServerError(supaErr.message || i18n.t("auth.errors.googleSignUpFailed"))
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
    handleChange,
    handleSubmit,
    handleGoogleSignUp,
  }
}
