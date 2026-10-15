import { useCallback, useState } from "react"
import { useAuth } from "@/context/useAuth"
import { makeRegisterSchema } from "@/lib/validations/auth"
import i18n, { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"
import { authErrorMessage, isDuplicateEmail } from "@/lib/authError"
import { usePasswordAffordances } from "@/components/auth/usePasswordAffordances"

export type FormState = {
  full_name: string
  email: string
  password: string
}

const EMPTY_FORM: FormState = { full_name: "", email: "", password: "" }

/** The confirmation mail that went out, as the screen after the form shows it. */
export interface SentMail {
  email: string
  /** An unconfirmed account already had this address; its first password stands. */
  repeated: boolean
}

const SENT_KEY = "equip:signupSent"

/**
 * The "check your email" screen outlives a reload. It used to vanish into an
 * empty form, and the person — waiting on a mail, refreshing the tab — had
 * no resend button and no idea which address they had typed. Kept by the tab
 * only: it names an address, and nobody else at this computer needs it.
 */
function readSent(): SentMail | null {
  try {
    const raw = sessionStorage.getItem(SENT_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") return null
    const { email, repeated } = parsed as Partial<SentMail>
    return typeof email === "string" ? { email, repeated: repeated === true } : null
  } catch {
    return null
  }
}

function writeSent(sent: SentMail | null): void {
  try {
    if (sent) sessionStorage.setItem(SENT_KEY, JSON.stringify(sent))
    else sessionStorage.removeItem(SENT_KEY)
  } catch {
    /* storage blocked: the screen just does not survive a reload */
  }
}

/**
 * Registration form state machine: the form, its per-field errors, and the
 * two places it can end — a mail sent (`sent`), or an address that already
 * has an account (`duplicateEmail`).
 */
export function useRegister() {
  const { register, signInWithGoogle } = useAuth()
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({})
  const [serverError, setServerError] = useState("")
  const [duplicateEmail, setDuplicateEmail] = useState(false)
  const [sent, setSent] = useState<SentMail | null>(readSent)
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const setPassword = useCallback((value: string) => {
    setForm((prev) => ({ ...prev, password: value }))
    setErrors((prev) => ({ ...prev, password: undefined }))
  }, [])
  const { showPassword, passwordGenerated, toggleShowPassword, generate, noteEdited } =
    usePasswordAffordances(setPassword)

  const handleChange = useCallback(
    (field: keyof FormState, value: string) => {
      setForm((prev) => ({ ...prev, [field]: value }))
      setErrors((prev) => ({ ...prev, [field]: undefined }))
      // Typing over a generated password makes the "save it" note stale.
      if (field === "password") noteEdited()
    },
    [noteEdited],
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
      // The language the form was rendered in becomes the profile's; the
      // trigger whitelists it against the same set as the DB CHECK.
      const preferredLocale = isSupportedLocale(i18n.resolvedLanguage) ? i18n.resolvedLanguage : DEFAULT_LOCALE
      const { repeated } = await register(
        result.data.email,
        result.data.password,
        result.data.full_name,
        preferredLocale,
      )
      const mail = { email: result.data.email, repeated }
      writeSent(mail)
      setSent(mail)
    } catch (err) {
      if (isDuplicateEmail(err)) {
        // Its own screen, not a red sentence — the reader almost certainly
        // has an account and wants to sign in, not an error.
        setForm((prev) => ({ ...prev, email: result.data.email }))
        setDuplicateEmail(true)
      } else {
        // Translated; the server's English goes to the dev console only.
        setServerError(authErrorMessage(err, "auth.errors.registrationFailed"))
      }
    } finally {
      setLoading(false)
    }
  }, [form, register])

  /** Back to the form, to correct the address the mail went to. */
  const changeAddress = useCallback(() => {
    setForm((prev) => ({ ...prev, email: sent?.email ?? prev.email, password: "" }))
    writeSent(null)
    setSent(null)
  }, [sent])

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
    sent,
    loading,
    googleLoading,
    showPassword,
    passwordGenerated,
    toggleShowPassword,
    handleGeneratePassword: generate,
    handleChange,
    handleSubmit,
    handleGoogleSignUp,
    changeAddress,
  }
}
