import { Link, Navigate } from "react-router-dom"
import { Trans, useTranslation } from "react-i18next"
import { CheckCircle2, Loader2, MailCheck, XCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import AuthLayout from "@/components/layout/AuthLayout"
import { PasswordFields } from "@/components/auth/PasswordFields"
import { GoogleIcon } from "@/pages/Auth/register/GoogleIcon"
import { ROLE_I18N_KEY } from "@/lib/roles"
import { useAcceptInvite } from "./useAcceptInvite"

/**
 * Public /invite/accept?token=... route -- reads the token, previews the
 * invite (email/role/validity), then either shows a signup form (not
 * authenticated), an "Accept" button (already signed in under the
 * matching email), or a terminal state (invalid/expired/mismatch/done).
 */
export default function AcceptInvite() {
  const { t } = useTranslation()
  const {
    phase,
    preview,
    form,
    errors,
    serverError,
    submitting,
    googleLoading,
    acceptedRole,
    currentUserEmail,
    passwordAffordances,
    handleChange,
    handleSubmit,
    handleGoogleSignUp,
    acceptNow,
    logout,
  } = useAcceptInvite()

  if (phase === "loading") {
    return (
      <AuthLayout heading={t("invite.heading")}>
        <div className="flex justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden />
        </div>
      </AuthLayout>
    )
  }

  if (phase === "invalid" || phase === "unusable") {
    return (
      <AuthLayout heading={t("invite.heading")}>
        <div className="flex flex-col items-center gap-4 py-4 text-center animate-fade-in">
          <div className="flex h-16 w-16 items-center justify-center rounded-md bg-destructive/10">
            <XCircle className="h-8 w-8 text-destructive-ink" strokeWidth={1.75} aria-hidden />
          </div>
          <p className="text-sm text-ink-muted leading-relaxed">
            {phase === "invalid" ? t("invite.errors.notFound") : t("invite.errors.unusable")}
          </p>
          <Link to="/login" className="block w-full">
            <Button variant="outline" size="lg" className="w-full">
              {t("authRegister.duplicate.goToSignIn")}
            </Button>
          </Link>
        </div>
      </AuthLayout>
    )
  }

  if (phase === "awaitingConfirmation") {
    return (
      <AuthLayout heading={t("invite.heading")}>
        <div className="flex flex-col items-center gap-4 py-4 text-center animate-fade-in">
          <div className="flex h-16 w-16 items-center justify-center rounded-md bg-brand/10">
            <MailCheck className="h-8 w-8 text-brand-ink" strokeWidth={1.75} aria-hidden />
          </div>
          <p className="text-sm text-ink-muted leading-relaxed">
            <Trans
              i18nKey="authRegister.success.body"
              values={{ email: preview?.email }}
              components={{ strong: <strong className="text-ink" /> }}
            />
            <br />
            {t("invite.confirmThenReturn")}
          </p>
        </div>
      </AuthLayout>
    )
  }

  if (phase === "done") {
    return (
      <AuthLayout heading={t("invite.heading")}>
        <div className="flex flex-col items-center gap-4 py-4 text-center animate-fade-in">
          <div className="flex h-16 w-16 items-center justify-center rounded-md bg-success/10">
            <CheckCircle2 className="h-8 w-8 text-success-ink" strokeWidth={1.75} aria-hidden />
          </div>
          <p className="text-sm text-ink-muted leading-relaxed">
            {acceptedRole
              ? t("invite.acceptedAs", { role: t(ROLE_I18N_KEY[acceptedRole as "teacher" | "student"]) })
              : t("invite.accepted")}
          </p>
          <Link to="/" className="block w-full">
            <Button size="lg" className="w-full">
              {t("invite.goToDashboard")}
            </Button>
          </Link>
        </div>
      </AuthLayout>
    )
  }

  if (phase === "mismatch") {
    return (
      <AuthLayout heading={t("invite.heading")}>
        <div className="flex flex-col items-center gap-4 py-4 text-center animate-fade-in">
          <div className="flex h-16 w-16 items-center justify-center rounded-md bg-warning/10">
            <XCircle className="h-8 w-8 text-warning-ink" strokeWidth={1.75} aria-hidden />
          </div>
          <p className="text-sm text-ink-muted leading-relaxed">
            <Trans
              i18nKey="invite.errors.emailMismatchDetail"
              values={{ invited: preview?.email, current: currentUserEmail }}
              components={{ strong: <strong className="text-ink" /> }}
            />
          </p>
          <Button variant="outline" size="lg" className="w-full" onClick={() => void logout()}>
            {t("invite.logOutAndSwitch")}
          </Button>
        </div>
      </AuthLayout>
    )
  }

  if (phase === "ready" && preview) {
    return (
      <AuthLayout heading={t("invite.heading")}>
        <div className="flex flex-col items-center gap-4 py-4 text-center animate-fade-in">
          {serverError && (
            <div role="alert" className="w-full text-sm text-destructive-ink bg-destructive/10 border border-destructive/20 p-3 rounded-lg">
              {serverError}
            </div>
          )}
          <p className="text-sm text-ink-muted leading-relaxed">
            <Trans
              i18nKey="invite.readyBody"
              values={{ email: currentUserEmail, role: t(ROLE_I18N_KEY[preview.role]) }}
              components={{ strong: <strong className="text-ink" /> }}
            />
          </p>
          <Button size="lg" className="w-full" onClick={() => void acceptNow()} disabled={phase !== "ready"}>
            {t("invite.acceptButton")}
          </Button>
        </div>
      </AuthLayout>
    )
  }

  if (phase === "accepting") {
    return (
      <AuthLayout heading={t("invite.heading")}>
        <div className="flex justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-ink-muted" aria-hidden />
        </div>
      </AuthLayout>
    )
  }

  // phase === "form": not authenticated -- signup form bound to the
  // invited email + role.
  if (!preview) return <Navigate to="/login" replace />

  return (
    <AuthLayout
      heading={t("invite.heading")}
      subheading={t("invite.formSubheading", { role: t(ROLE_I18N_KEY[preview.role]) })}
    >
      <div className="space-y-6 animate-fade-in">
        {serverError && (
          <div role="alert" className="text-sm text-destructive-ink bg-destructive/10 border border-destructive/20 p-3 rounded-lg">
            {serverError}
          </div>
        )}

        <Button
          type="button"
          variant="outline"
          size="lg"
          className="w-full font-medium rounded-md"
          onClick={() => void handleGoogleSignUp()}
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

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-surface px-3 text-ink-muted">{t("authRegister.orRegisterEmail")}</span>
          </div>
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

          <Button type="submit" size="lg" className="w-full" disabled={submitting}>
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
