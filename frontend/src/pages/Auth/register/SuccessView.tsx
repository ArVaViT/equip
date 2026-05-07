import { Link } from "react-router-dom"
import { ArrowLeft, Clock, MailCheck } from "lucide-react"
import { Trans, useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import AuthLayout from "@/components/layout/AuthLayout"

interface Props {
  email: string
  isTeacher: boolean
}

/**
 * Post-register confirmation screen. Teachers get a second banner that
 * explains the additional admin-approval step before the course-creation
 * tools unlock.
 */
export function SuccessView({ email, isTeacher }: Props) {
  const { t } = useTranslation()
  return (
    <AuthLayout
      heading={
        isTeacher
          ? t("authRegister.success.headingTeacher")
          : t("authRegister.success.headingDefault")
      }
      subheading={
        isTeacher
          ? t("authRegister.success.subheadingTeacher")
          : t("authRegister.success.subheadingDefault")
      }
    >
      <div className="space-y-6 animate-fade-in">
        <div className="flex flex-col items-center text-center gap-4 py-4">
          <div
            className={`flex h-16 w-16 items-center justify-center rounded-md ${
              isTeacher ? "bg-warning/10" : "bg-primary/10"
            }`}
          >
            {isTeacher ? (
              <Clock className="h-8 w-8 text-warning" strokeWidth={1.75} aria-hidden />
            ) : (
              <MailCheck className="h-8 w-8 text-primary" strokeWidth={1.75} aria-hidden />
            )}
          </div>
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground leading-relaxed">
              <Trans
                i18nKey="authRegister.success.body"
                values={{ email }}
                components={{ strong: <strong className="text-foreground" /> }}
              />
              <br />
              {t("authRegister.success.clickLinkToActivate")}
            </p>
            {isTeacher && (
              <div className="mt-4 rounded-md border border-border border-l-[3px] border-l-warning bg-warning/5 p-3">
                <p className="text-sm leading-relaxed text-foreground">
                  {t("authRegister.success.teacherApprovalBanner")}
                </p>
              </div>
            )}
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
