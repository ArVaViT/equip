import { Link } from "react-router-dom"
import { Mail } from "lucide-react"
import { Trans, useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import AuthLayout from "@/components/layout/AuthLayout"
import { SUPPORT_EMAIL } from "@/lib/brand"

/**
 * Terminal state shown when the register endpoint reports a duplicate
 * email. We can't tell whether it was a typo or a genuine prior
 * registration, so surface all three recovery paths (login, reset, support)
 * instead of forcing one.
 */
export function DuplicateEmailView({ email }: { email: string }) {
  const { t } = useTranslation()
  return (
    <AuthLayout
      heading={t("authRegister.duplicate.heading")}
      subheading={t("authRegister.duplicate.subheading")}
    >
      <div className="space-y-6 animate-fade-in">
        <div className="flex flex-col items-center text-center gap-4 py-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-md bg-warning/10">
            <Mail className="h-8 w-8 text-warning" strokeWidth={1.75} aria-hidden />
          </div>
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground leading-relaxed">
              <Trans
                i18nKey="authRegister.duplicate.bodyExists"
                values={{ email }}
                components={{ strong: <strong className="text-foreground" /> }}
              />
            </p>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {t("authRegister.duplicate.bodyHint")}
            </p>
          </div>
        </div>
        <div className="space-y-3">
          <Link to="/login" className="block">
            <Button size="lg" className="w-full">
              {t("authRegister.duplicate.goToSignIn")}
            </Button>
          </Link>
          <Link to="/forgot-password" className="block">
            <Button variant="outline" size="lg" className="w-full">
              {t("authRegister.duplicate.forgotPassword")}
            </Button>
          </Link>
          <a href={`mailto:${SUPPORT_EMAIL}`} className="block">
            <Button variant="ghost" size="lg" className="w-full text-muted-foreground">
              {t("authRegister.duplicate.contactSupport")}
            </Button>
          </a>
        </div>
      </div>
    </AuthLayout>
  )
}
