import { Link } from "react-router-dom"
import { Trans, useTranslation } from "react-i18next"
import { Loader2, XCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import AuthLayout from "@/components/layout/AuthLayout"
import { PasswordFields } from "@/components/auth/PasswordFields"
import { GoogleIcon } from "@/pages/Auth/register/GoogleIcon"
import type { InvitationPreview } from "@/services/invitations"
import { useAcceptInvite } from "./useAcceptInvite"

/** Who is inviting, and to what — the first thing a person reads here. */
function invitedBy(preview: InvitationPreview, t: (key: string, values?: Record<string, unknown>) => string): string {
  const organization = preview.organization_name
  if (!organization) return t("invite.from.platform")
  if (preview.scope === "course") {
    return preview.course_title
      ? t("invite.from.course", { organization, course: preview.course_title })
      : t("invite.from.courseUntitled", { organization })
  }
  return t(preview.role === "teacher" ? "invite.from.teach" : "invite.from.study", { organization })
}

/**
 * Public /invite/accept#token=… (or ?token= from older letters).
 *
 * One screen per situation, and none of them waits on an email: the link
 * was delivered to the invited address, so it proves what a confirmation
 * would. No account yet → a form that creates one, signs in and goes
 * straight to what the invitation offered. An account → sign in (password
 * or Google) and the page accepts on its own. Signed in already → accepted
 * on arrival.
 */
export default function AcceptInvite() {
  const { t } = useTranslation()
  const {
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
    currentUserEmail,
    passwordAffordances,
    handleChange,
    handleSubmit,
    handleGoogle,
    logout,
  } = useAcceptInvite()

  const heading = t("invite.heading")
  const subheading = preview ? invitedBy(preview, t) : undefined

  if (phase === "loading" || phase === "accepting") {
    return (
      <AuthLayout heading={heading} subheading={subheading}>
        <div className="flex justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-ink-muted" strokeWidth={1.75} aria-hidden />
        </div>
      </AuthLayout>
    )
  }

  const notice = (message: React.ReactNode, tone: "warning" | "destructive") => (
    <div className="flex flex-col items-center gap-4 py-4 text-center animate-fade-in">
      <div
        className={
          tone === "warning"
            ? "flex h-16 w-16 items-center justify-center rounded-md bg-warning/10"
            : "flex h-16 w-16 items-center justify-center rounded-md bg-destructive/10"
        }
      >
        <XCircle
          className={tone === "warning" ? "h-8 w-8 text-warning-ink" : "h-8 w-8 text-destructive-ink"}
          strokeWidth={1.75}
          aria-hidden
        />
      </div>
      <p role="alert" className="text-sm text-ink-muted leading-relaxed">
        {message}
      </p>
    </div>
  )

  if (phase === "unavailable" || phase === "acceptFailed") {
    return (
      <AuthLayout heading={heading} subheading={subheading}>
        {notice(phase === "unavailable" ? previewError : t("invite.errors.acceptFailed"), "warning")}
        <Button size="lg" className="w-full" onClick={phase === "unavailable" ? retryPreview : retryAccept}>
          {t("common.tryAgain")}
        </Button>
      </AuthLayout>
    )
  }

  if (phase === "invalid") {
    return (
      <AuthLayout heading={heading}>
        {notice(t("invite.errors.notFound"), "destructive")}
      </AuthLayout>
    )
  }

  if (phase === "unusable" && reason) {
    return (
      <AuthLayout heading={heading} subheading={subheading}>
        {notice(t(`invite.unusable.${reason}`), reason === "used" ? "warning" : "destructive")}
        {/* Only a used link has a next step on this screen; the others are
            a word to whoever sent it, and the copy says so. */}
        {reason === "used" && (
          <Link to={currentUserEmail ? "/" : "/login"} className="block w-full">
            <Button size="lg" className="w-full">
              {currentUserEmail ? t("invite.goToDashboard") : t("auth.signIn")}
            </Button>
          </Link>
        )}
      </AuthLayout>
    )
  }

  if (phase === "mismatch" && preview) {
    return (
      <AuthLayout heading={heading} subheading={subheading}>
        {notice(
          <Trans
            i18nKey="invite.errors.emailMismatchDetail"
            values={{ invited: preview.email, current: currentUserEmail }}
            components={{ strong: <strong className="text-ink" /> }}
          />,
          "warning",
        )}
        <Button variant="outline" size="lg" className="w-full" onClick={() => void logout()}>
          {t("invite.logOutAndSwitch")}
        </Button>
      </AuthLayout>
    )
  }

  if (!preview) return null

  const googleButton = (
    <Button
      type="button"
      variant="outline"
      size="lg"
      className="w-full font-medium rounded-md"
      onClick={() => void handleGoogle()}
      disabled={googleLoading || submitting}
    >
      {googleLoading ? (
        <>
          <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} />
          {t("auth.connecting")}
        </>
      ) : (
        <>
          <GoogleIcon className="h-4 w-4 mr-2.5" />
          {t("auth.continueWithGoogle")}
        </>
      )}
    </Button>
  )

  const errorBox = serverError && (
    <div role="alert" className="text-sm text-destructive-ink bg-destructive/10 border border-destructive/20 p-3 rounded-lg">
      {serverError}
    </div>
  )

  if (phase === "signIn") {
    return (
      <AuthLayout heading={heading} subheading={subheading}>
        <div className="space-y-6 animate-fade-in">
          {errorBox}
          <p className="text-sm text-ink-muted leading-relaxed">
            <Trans
              i18nKey="invite.hasAccount"
              values={{ email: preview.email }}
              components={{ strong: <strong className="text-ink" /> }}
            />
          </p>
          {/* The sign-in page brings them back here, signed in, and this page
              accepts on its own. */}
          <Link to="/login" state={{ from: invitePath, email: preview.email }} className="block">
            <Button size="lg" className="w-full">
              {t("auth.signIn")}
            </Button>
          </Link>
          {googleButton}
        </div>
      </AuthLayout>
    )
  }

  // phase === "form": no account at the invited address yet.
  return (
    <AuthLayout heading={heading} subheading={subheading}>
      <div className="space-y-6 animate-fade-in">
        {errorBox}

        {googleButton}

        <div className="flex items-center gap-3 text-xs uppercase text-ink-muted">
          <div className="h-px flex-1 bg-border" />
          <span>{t("authRegister.orRegisterEmail")}</span>
          <div className="h-px flex-1 bg-border" />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            void handleSubmit()
          }}
          className="space-y-4"
        >
          <div className="space-y-2">
            <Label htmlFor="inviteEmail">{t("auth.email")}</Label>
            <Input id="inviteEmail" type="email" value={preview.email} disabled readOnly fieldSize="lg" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="fullName">{t("authRegister.fullName")}</Label>
            <Input
              id="fullName"
              placeholder={t("authRegister.fullNamePlaceholder")}
              autoComplete="name"
              fieldSize="lg"
              value={form.full_name}
              onChange={(e) => handleChange("full_name", e.target.value)}
              aria-invalid={!!errors.full_name}
              aria-describedby={errors.full_name ? "invite-fullName-error" : undefined}
              autoFocus
            />
            {errors.full_name && (
              <p id="invite-fullName-error" role="alert" className="text-xs text-destructive mt-1">
                {errors.full_name}
              </p>
            )}
          </div>

          <PasswordFields
            idPrefix="invite"
            password={form.password}
            confirmPassword={form.confirmPassword}
            passwordError={errors.password}
            confirmError={errors.confirmPassword}
            showPassword={passwordAffordances.showPassword}
            passwordGenerated={passwordAffordances.passwordGenerated}
            onChange={handleChange}
            onToggleShowPassword={passwordAffordances.toggleShowPassword}
            onGeneratePassword={passwordAffordances.generate}
          />

          <Button type="submit" size="lg" className="w-full" disabled={submitting || googleLoading}>
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} />
                {t("common.loading")}
              </>
            ) : (
              t("invite.createAccountButton")
            )}
          </Button>
        </form>
      </div>
    </AuthLayout>
  )
}
