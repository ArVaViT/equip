import { useCallback, useEffect, useState } from "react"
import { usePasswordAffordances } from "@/components/auth/usePasswordAffordances"
import { useSearchParams } from "react-router-dom"
import { useAuth } from "@/context/useAuth"
import { invitationsService, type InvitationPreview } from "@/services/invitations"
import { makeAcceptInviteSchema } from "@/lib/validations/auth"
import { setPendingInviteToken, takePendingInviteToken } from "@/lib/pendingInvite"
import { isAxiosError } from "axios"
import { getErrorCode } from "@/lib/errorCode"
import { getErrorDetail } from "@/lib/errorDetail"
import { authErrorMessage, isDuplicateEmail } from "@/lib/authError"
import i18n, { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"

export type FormState = {
  full_name: string
  password: string
  confirmPassword: string
}

const EMPTY_FORM: FormState = { full_name: "", password: "", confirmPassword: "" }

// A 404/410/409 from the preview or accept call all mean "this link
// can't be used" -- distinguished only by which copy to show.
export type AcceptInvitePhase =
  | "loading"
  | "invalid" // token doesn't exist
  | "unavailable" // the server did not answer; nothing is known about the link yet
  | "unusable" // expired, already accepted, or revoked
  | "form" // pending + valid, caller not authenticated yet -- show signup form
  | "mismatch" // pending + valid, but signed in under a different email
  | "ready" // pending + valid, signed in under the matching email -- show Accept button
  | "accepting"
  | "done" // accepted this session
  | "awaitingConfirmation" // email/password signup submitted, waiting on email confirm

export function useAcceptInvite() {
  const [params] = useSearchParams()
  const token = params.get("token") ?? ""
  const { user, register, signInWithGoogle, logout, refreshUser } = useAuth()

  const [preview, setPreview] = useState<InvitationPreview | null>(null)
  const [previewFailed, setPreviewFailed] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewAttempt, setPreviewAttempt] = useState(0)
  const [phase, setPhase] = useState<AcceptInvitePhase>("loading")
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({})
  const [serverError, setServerError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [acceptedRole, setAcceptedRole] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setPreviewFailed(true)
      setPhase("invalid")
      return
    }
    let cancelled = false
    setPreviewFailed(false)
    setPreviewError(null)
    invitationsService
      .previewInvitation(token)
      .then((data) => {
        if (cancelled) return
        setPreview(data)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        // Only the server saying «no such link» makes the link invalid. A
        // 500, a dropped connection or a rate limit used to read the same —
        // «ask the administrator to resend it» — for a link that was fine.
        const status = isAxiosError(err) ? err.response?.status : undefined
        if (status === 400 || status === 404 || status === 410 || status === 422) {
          setPreviewFailed(true)
        } else {
          setPreviewError(getErrorDetail(err, i18n.t("invite.errors.loadFailed")))
        }
      })
    return () => {
      cancelled = true
    }
  }, [token, previewAttempt])

  const retryPreview = useCallback(() => setPreviewAttempt((n) => n + 1), [])

  // Derive the phase from (preview, previewFailed, user) whenever any of
  // them change -- keeps the state machine in one place instead of
  // scattered across the fetch handler and the auth-watching effect.
  useEffect(() => {
    if (phase === "accepting" || phase === "done" || phase === "awaitingConfirmation") return
    if (previewError) {
      setPhase("unavailable")
      return
    }
    if (previewFailed) {
      setPhase("invalid")
      return
    }
    if (!preview) {
      setPhase("loading")
      return
    }
    if (preview.status !== "pending" || preview.is_expired) {
      setPhase("unusable")
      return
    }
    if (!user) {
      setPhase("form")
      return
    }
    setPhase(user.email.trim().toLowerCase() === preview.email.trim().toLowerCase() ? "ready" : "mismatch")
  }, [preview, previewFailed, previewError, user, phase])

  const acceptNow = useCallback(async () => {
    setPhase("accepting")
    setServerError("")
    try {
      const result = await invitationsService.acceptInvitation(token)
      setAcceptedRole(result.role)
      await refreshUser()
      setPhase("done")
    } catch (err) {
      const code = getErrorCode(err)
      setServerError(
        code === "invitation.email_mismatch"
          ? i18n.t("invite.errors.emailMismatch")
          : i18n.t("invite.errors.acceptFailed"),
      )
      setPhase("ready")
    }
  }, [token, refreshUser])

  const setBothPasswords = useCallback((value: string) => {
    setForm((prev) => ({ ...prev, password: value, confirmPassword: value }))
    setErrors((prev) => ({ ...prev, password: undefined, confirmPassword: undefined }))
  }, [])
  const passwordAffordances = usePasswordAffordances(setBothPasswords)

  const handleChange = useCallback((field: keyof FormState, value: string) => {
    if (field === "password" || field === "confirmPassword") passwordAffordances.noteEdited()
    setForm((prev) => ({ ...prev, [field]: value }))
    setErrors((prev) => ({ ...prev, [field]: undefined }))
  }, [passwordAffordances])

  const handleSubmit = useCallback(async () => {
    if (!preview) return
    setServerError("")
    const result = makeAcceptInviteSchema().safeParse(form)
    if (!result.success) {
      const fieldErrors: Partial<Record<string, string>> = {}
      for (const issue of result.error.issues) {
        const key = String(issue.path[0])
        if (!fieldErrors[key]) fieldErrors[key] = issue.message
      }
      setErrors(fieldErrors)
      return
    }
    setSubmitting(true)
    try {
      const preferredLocale = isSupportedLocale(i18n.resolvedLanguage) ? i18n.resolvedLanguage : DEFAULT_LOCALE
      // Persisted BEFORE register() -- email confirmation is required
      // (see SuccessView), so there's no active session yet to redeem
      // the token with. App.tsx's resume effect picks this up once the
      // user comes back signed in after confirming.
      setPendingInviteToken(token)
      await register(preview.email, result.data.password, result.data.full_name, preferredLocale)
      setPhase("awaitingConfirmation")
    } catch (err: unknown) {
      // register() failed -- there's no pending redirect coming, so drop
      // the stashed token rather than leaving it to misfire on some
      // unrelated later sign-in.
      takePendingInviteToken()
      // An invited person is being asked to create an account they were
      // told to expect; getting an English GoTrue sentence back on a
      // German invitation page is the worst possible first impression of a
      // school that invited them. Translate, always.
      setServerError(
        isDuplicateEmail(err)
          ? i18n.t("invite.errors.accountExists")
          : authErrorMessage(err, "auth.errors.registrationFailed"),
      )
    } finally {
      setSubmitting(false)
    }
  }, [form, preview, register, token])

  const handleGoogleSignUp = useCallback(async () => {
    setGoogleLoading(true)
    try {
      setPendingInviteToken(token)
      await signInWithGoogle()
    } catch (err: unknown) {
      takePendingInviteToken()
      setServerError(authErrorMessage(err, "auth.errors.googleSignUpFailed"))
      setGoogleLoading(false)
    }
  }, [signInWithGoogle, token])

  return {
    previewError,
    retryPreview,
    phase,
    preview,
    form,
    errors,
    serverError,
    submitting,
    googleLoading,
    acceptedRole,
    currentUserEmail: user?.email ?? null,
    passwordAffordances,
    handleChange,
    handleSubmit,
    handleGoogleSignUp,
    acceptNow,
    logout,
  }
}
