import { useCallback, useEffect, useRef, useState } from "react"
import { usePasswordAffordances } from "@/components/auth/usePasswordAffordances"
import { useLocation, useNavigate } from "react-router-dom"
import { useAuth } from "@/context/useAuth"
import {
  invitationsService,
  type AcceptedInvitation,
  type InvitationPreview,
  type InvitationUnusableReason,
} from "@/services/invitations"
import { makeAcceptInviteSchema } from "@/lib/validations/auth"
import { inviteAcceptPath, inviteTokenFrom, inviteTokenIsInQuery } from "@/lib/inviteLink"
import { rememberReturnPath } from "@/lib/authRedirect"
import { isAxiosError } from "axios"
import { enrollmentsChanged } from "@/lib/enrollmentsChanged"
import { getErrorCode } from "@/lib/errorCode"
import { getErrorDetail } from "@/lib/errorDetail"
import { authErrorMessage } from "@/lib/authError"
import i18n, { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"

export type FormState = {
  full_name: string
  password: string
  confirmPassword: string
}

const EMPTY_FORM: FormState = { full_name: "", password: "", confirmPassword: "" }

export type AcceptInvitePhase =
  | "loading"
  | "invalid" // no such link
  | "unavailable" // the server did not answer; nothing is known about the link yet
  | "unusable" // the link admits nobody now -- `reason` says why
  | "form" // nobody signed in, no account at this address: create one here
  | "signIn" // nobody signed in, the address has an account: sign in, then this page accepts
  | "mismatch" // signed in under another address
  | "accepting" // signed in under this address: accepting, then off to what it offered
  | "acceptFailed" // accepting failed for a reason with no screen of its own

/** Where an accepted invitation leads: the course it seated them on, or home. */
function destinationOf(result: AcceptedInvitation): string {
  return result.enrolled_course_id ? `/courses/${result.enrolled_course_id}` : "/"
}

/**
 * Where to go once the session just signed in has loaded.
 *
 * Signing in makes the app swap every route for its spinner while it loads
 * the new profile, so this page unmounts between registering and arriving.
 * What it had decided must outlive it — in memory, for this page load only,
 * and only for the same link.
 */
let afterSignIn: { token: string; path: string } | null = null

/** The server's refusals that have a screen of their own. */
function reasonFor(code: string | null, status: number | undefined): InvitationUnusableReason | null {
  if (code === "invitation.expired") return "expired"
  if (code === "invitation.already_used") return "used"
  if (code === "invitation.inviter_not_staff") return "inviter_left"
  // The course an invitation seats on is the only thing it can 404 on
  // besides the token itself, which has its own code.
  if (code === "resource.not_found" || (status === 404 && code !== "invitation.not_found")) return "course_gone"
  return null
}

export function useAcceptInvite() {
  const location = useLocation()
  const navigate = useNavigate()
  const token = inviteTokenFrom(location)
  const tokenInQuery = inviteTokenIsInQuery(location)
  const { user, login, signInWithGoogle, logout, refreshUser } = useAuth()

  const [preview, setPreview] = useState<InvitationPreview | null>(null)
  const [missing, setMissing] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [previewAttempt, setPreviewAttempt] = useState(0)
  // What the server said after the preview, which outranks it.
  const [refusal, setRefusal] = useState<InvitationUnusableReason | null>(null)
  const [accountExists, setAccountExists] = useState(false)
  const [acceptFailed, setAcceptFailed] = useState(false)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<Partial<Record<string, string>>>({})
  const [serverError, setServerError] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const acceptStarted = useRef(false)

  const invitePath = (() => {
    const { pathname, hash } = inviteAcceptPath(token)
    return `${pathname}#${hash}`
  })()

  // A letter sent before 2026-09-16 put the token in the query. The page
  // load that brought it here is already in the edge log, but moving it to
  // the fragment keeps it out of the Referer of every request this page
  // makes from now on, and out of the address a person copies to ask for
  // help. Same token, same page, no reload.
  useEffect(() => {
    if (tokenInQuery) navigate(inviteAcceptPath(token), { replace: true })
  }, [tokenInQuery, token, navigate])

  // Back from signing in with the password just chosen: the invitation was
  // accepted when the account was made, so straight on to what it offered.
  useEffect(() => {
    if (!user || afterSignIn?.token !== token) return
    const { path } = afterSignIn
    afterSignIn = null
    navigate(path, { replace: true })
  }, [user, token, navigate])

  useEffect(() => {
    if (!token) {
      setMissing(true)
      return
    }
    let cancelled = false
    setMissing(false)
    setPreviewError(null)
    invitationsService
      .previewInvitation(token)
      .then((data) => {
        if (!cancelled) setPreview(data)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        // Only the server saying «no such link» makes the link invalid. A
        // 500, a dropped connection or a rate limit used to read the same —
        // «ask the administrator to resend it» — for a link that was fine.
        const status = isAxiosError(err) ? err.response?.status : undefined
        if (status === 400 || status === 404 || status === 410 || status === 422) {
          setMissing(true)
        } else {
          setPreviewError(getErrorDetail(err, i18n.t("invite.errors.loadFailed")))
        }
      })
    return () => {
      cancelled = true
    }
  }, [token, previewAttempt])

  const retryPreview = useCallback(() => setPreviewAttempt((n) => n + 1), [])

  const reason: InvitationUnusableReason | null =
    refusal ?? preview?.unusable_reason ?? (preview?.is_expired ? "expired" : null)
  const sameAddress =
    !!user && !!preview && user.email.trim().toLowerCase() === preview.email.trim().toLowerCase()

  const phase: AcceptInvitePhase = (() => {
    if (!token || missing) return "invalid"
    if (previewError) return "unavailable"
    if (!preview || afterSignIn?.token === token) return "loading"
    if (reason) return "unusable"
    if (user) {
      if (!sameAddress) return "mismatch"
      return acceptFailed ? "acceptFailed" : "accepting"
    }
    return preview.has_account || accountExists ? "signIn" : "form"
  })()

  const showRefusal = useCallback((err: unknown): boolean => {
    const code = getErrorCode(err)
    const status = isAxiosError(err) ? err.response?.status : undefined
    if (code === "invitation.not_found") {
      setMissing(true)
      return true
    }
    const refused = reasonFor(code, status)
    if (refused) setRefusal(refused)
    return refused !== null
  }, [])

  const accept = useCallback(async () => {
    setAcceptFailed(false)
    try {
      const result = await invitationsService.acceptInvitation(token)
      // The dashboard reads enrollments in an effect keyed on the user and
      // the locale; accepting moves neither, so without this it keeps the
      // empty state it loaded before and only a refresh shows the course.
      enrollmentsChanged()
      // A teaching invitation changes the role the header and the gates read.
      await refreshUser()
      navigate(destinationOf(result), { replace: true })
    } catch (err) {
      if (!showRefusal(err)) setAcceptFailed(true)
    }
  }, [token, refreshUser, navigate, showRefusal])

  // Signed in under the invited address -- by Google, by the sign-in page,
  // or already: nothing is left to decide, so the page accepts on its own.
  useEffect(() => {
    if (phase !== "accepting" || acceptStarted.current) return
    acceptStarted.current = true
    void accept()
  }, [phase, accept])

  const retryAccept = useCallback(() => void accept(), [accept])

  const setBothPasswords = useCallback((value: string) => {
    setForm((prev) => ({ ...prev, password: value, confirmPassword: value }))
    setErrors((prev) => ({ ...prev, password: undefined, confirmPassword: undefined }))
  }, [])
  const passwordAffordances = usePasswordAffordances(setBothPasswords)

  const handleChange = useCallback(
    (field: keyof FormState, value: string) => {
      if (field === "password" || field === "confirmPassword") passwordAffordances.noteEdited()
      setForm((prev) => ({ ...prev, [field]: value }))
      setErrors((prev) => ({ ...prev, [field]: undefined }))
    },
    [passwordAffordances],
  )

  const handleSubmit = useCallback(async () => {
    if (!preview) return
    setServerError("")
    const parsed = makeAcceptInviteSchema().safeParse(form)
    if (!parsed.success) {
      const fieldErrors: Partial<Record<string, string>> = {}
      for (const issue of parsed.error.issues) {
        const key = String(issue.path[0])
        if (!fieldErrors[key]) fieldErrors[key] = issue.message
      }
      setErrors(fieldErrors)
      return
    }
    setSubmitting(true)
    const locale = isSupportedLocale(i18n.resolvedLanguage) ? i18n.resolvedLanguage : DEFAULT_LOCALE
    let result: AcceptedInvitation
    try {
      result = await invitationsService.registerByInvitation(
        token,
        parsed.data.full_name,
        parsed.data.password,
        locale,
      )
    } catch (err) {
      setSubmitting(false)
      const code = getErrorCode(err)
      if (code === "invitation.account_exists") {
        setAccountExists(true)
      } else if (code === "auth.weak_password") {
        setErrors({ password: i18n.t("auth.errors.weakPassword") })
      } else if (!showRefusal(err)) {
        // A 429 from our own limiter, or the sign-in service not answering.
        const status = isAxiosError(err) ? err.response?.status : undefined
        setServerError(i18n.t(status === 429 ? "auth.errors.rateLimited" : "auth.errors.serverError"))
      }
      return
    }
    const path = destinationOf(result)
    afterSignIn = { token, path }
    try {
      await login(result.email, parsed.data.password)
    } catch {
      // The account exists and holds this invitation; only the sign-in
      // failed. The sign-in page, pre-filled, takes them the rest of the way.
      afterSignIn = null
      navigate("/login", { replace: true, state: { from: path, email: result.email } })
    }
  }, [form, preview, token, login, navigate, showRefusal])

  const handleGoogle = useCallback(async () => {
    setGoogleLoading(true)
    setServerError("")
    // Google comes back to /auth/callback in a fresh page load; this tab is
    // sent back here, signed in, and the page accepts on its own.
    rememberReturnPath({ from: invitePath })
    try {
      await signInWithGoogle()
    } catch (err: unknown) {
      setServerError(authErrorMessage(err, "auth.errors.googleSignUpFailed"))
      setGoogleLoading(false)
    }
  }, [signInWithGoogle, invitePath])

  return {
    phase,
    reason,
    preview,
    previewError,
    retryPreview,
    retryAccept,
    form,
    errors,
    serverError,
    submitting,
    googleLoading,
    invitePath,
    currentUserEmail: user?.email ?? null,
    passwordAffordances,
    handleChange,
    handleSubmit,
    handleGoogle,
    logout,
  }
}

/** Test-only: forget a sign-in this "page load" was waiting on. */
export function resetAcceptInviteForTests(): void {
  afterSignIn = null
}
