import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import AuthLayout from "@/components/layout/AuthLayout"
import { useAuth } from "@/context/useAuth"

interface Props {
  email: string
  /** Router state of the register page — where the visitor was going. */
  state: unknown
}

/**
 * The address already has an account. One thing to do — sign in, with the
 * address filled in — and the two ways round a forgotten password beside it.
 */
export function DuplicateEmailView({ email, state }: Props) {
  const { t } = useTranslation()
  const { signInWithGoogle } = useAuth()
  const from = state && typeof state === "object" ? (state as { from?: unknown }).from : undefined
  return (
    <AuthLayout heading={t("authRegister.duplicate.heading")}>
      <div className="space-y-5 animate-fade-in">
        <p className="text-sm text-ink-muted leading-relaxed break-words">
          <strong className="text-ink">{email}</strong>
        </p>
        <Link to="/login" state={{ email, from }} className="block">
          <Button size="lg" className="w-full">
            {t("auth.signIn")}
          </Button>
        </Link>
        <p className="text-center text-sm text-ink-muted">
          <button
            type="button"
            onClick={() => void signInWithGoogle().catch(() => undefined)}
            className="text-brand transition-colors hover:text-brand-ink"
          >
            {t("authRegister.duplicate.withGoogle")}
          </button>
          {" · "}
          <Link to="/forgot-password" state={{ email }} className="text-brand transition-colors hover:text-brand-ink">
            {t("auth.forgotPasswordLink")}
          </Link>
        </p>
      </div>
    </AuthLayout>
  )
}
