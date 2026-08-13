import { Link } from "react-router-dom"
import { ArrowLeft, MailCheck } from "lucide-react"
import { Trans, useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import AuthLayout from "@/components/layout/AuthLayout"

interface Props {
  email: string
}

/**
 * Post-register confirmation screen. Self-service signups are all
 * students; teacher promotion is admin-only, so the post-register
 * surface no longer needs the pending-teacher branch.
 */
export function SuccessView({ email }: Props) {
  const { t } = useTranslation()
  return (
    <AuthLayout
      heading={t("authRegister.success.headingDefault")}
      subheading={t("authRegister.success.subheadingDefault")}
    >
      <div className="space-y-6 animate-fade-in">
        <div className="flex flex-col items-center text-center gap-4 py-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-md bg-brand/10">
            <MailCheck className="h-8 w-8 text-brand-ink" strokeWidth={1.75} aria-hidden />
          </div>
          <div className="space-y-2">
            <p className="text-sm text-ink-muted leading-relaxed">
              <Trans
                i18nKey="authRegister.success.body"
                values={{ email }}
                components={{ strong: <strong className="text-ink" /> }}
              />
              <br />
              {t("authRegister.success.clickLinkToActivate")}
            </p>
          </div>
        </div>
        <Link to="/login" className="block">
          <Button variant="outline" size="lg" className="w-full">
            <ArrowLeft className="h-4 w-4 mr-2" strokeWidth={1.75} aria-hidden />
            {t("authRegister.success.backToSignIn")}
          </Button>
        </Link>
      </div>
    </AuthLayout>
  )
}
