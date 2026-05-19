import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Award, BookOpen, CheckCircle, GraduationCap, Mail, XCircle, Clock } from "lucide-react"
import type { Certificate } from "@/types"
import { formatDateTime, formatRelative } from "@/i18n/format"

export type AdminCert = Certificate

interface Props {
  certs: AdminCert[]
  actionId: string | null
  onApprove: (certId: string) => void
  onReject: (certId: string) => void
}

/** Certificates pending final admin approval after a teacher signed off. */
export function PendingCertsCard({ certs, actionId, onApprove, onReject }: Props) {
  const { t } = useTranslation()
  if (certs.length === 0) return null

  return (
    <Card className="mb-6 border-l-stripe border-l-primary">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <Award className="h-4 w-4 text-primary" strokeWidth={1.75} aria-hidden />
          {t("admin.pendingCerts.title")}
          <Badge variant="default" className="font-normal">
            {certs.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="space-y-3">
          {certs.map((cert) => (
            <article
              key={cert.id}
              className="flex flex-col gap-3 rounded-md border border-l-stripe border-l-primary/60 bg-primary/5 p-4 sm:flex-row sm:items-stretch sm:gap-4"
            >
              {/* Identity column — student + course as the two top-level
                  facts the admin needs to recognise this request. */}
              <div className="min-w-0 flex-1 space-y-2">
                <div>
                  <p className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                    <GraduationCap className="h-3.5 w-3.5 text-primary shrink-0" strokeWidth={1.75} aria-hidden />
                    <span className="truncate">{cert.student_name || t("admin.pendingCerts.studentFallback")}</span>
                  </p>
                  {cert.student_email && (
                    <p className="ml-5 flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Mail className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden />
                      <span className="truncate">{cert.student_email}</span>
                    </p>
                  )}
                </div>
                <p className="flex items-center gap-1.5 text-xs text-foreground/80">
                  <BookOpen className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.75} aria-hidden />
                  <span className="truncate">{cert.course_title || t("admin.pendingCerts.courseFallback")}</span>
                </p>
                {/* Timeline of the request lifecycle so the admin knows
                    how long this has been waiting and who's already
                    signed off (the teacher must approve before this
                    list shows the row). */}
                <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-[11px] text-muted-foreground/90 sm:grid-cols-2">
                  {cert.requested_at && (
                    <div className="flex items-center gap-1.5">
                      <Clock className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden />
                      <span>
                        {t("admin.pendingCerts.requestedRelative", {
                          relative: formatRelative(cert.requested_at),
                        })}
                      </span>
                    </div>
                  )}
                  {cert.teacher_approved_at && cert.teacher_approver_name && (
                    <div className="flex items-center gap-1.5">
                      <CheckCircle className="h-3 w-3 shrink-0 text-success" strokeWidth={1.75} aria-hidden />
                      <span>
                        {t("admin.pendingCerts.teacherSignOff", {
                          name: cert.teacher_approver_name,
                          relative: formatRelative(cert.teacher_approved_at),
                        })}
                      </span>
                    </div>
                  )}
                  {cert.requested_at && (
                    <div
                      className="hidden text-[10px] text-muted-foreground/60 sm:col-span-2 sm:block"
                      title={cert.requested_at}
                    >
                      {t("admin.pendingCerts.requestedAtPrefix", {
                        ts: formatDateTime(cert.requested_at),
                      })}
                    </div>
                  )}
                </dl>
              </div>
              {/* Decision column — buttons + a small status hint so the
                  admin sees exactly what state this transitions to. */}
              <div className="flex shrink-0 flex-col items-stretch justify-center gap-2 sm:w-44">
                <Button
                  size="sm"
                  className="h-8"
                  onClick={() => onApprove(cert.id)}
                  disabled={actionId === cert.id}
                >
                  <CheckCircle className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  {t("admin.pendingCerts.approve")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-destructive hover:text-destructive"
                  onClick={() => onReject(cert.id)}
                  disabled={actionId === cert.id}
                >
                  <XCircle className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                  {t("admin.pendingCerts.reject")}
                </Button>
                <p className="text-[10px] leading-tight text-muted-foreground/80">
                  {t("admin.pendingCerts.approveHint")}
                </p>
              </div>
            </article>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
