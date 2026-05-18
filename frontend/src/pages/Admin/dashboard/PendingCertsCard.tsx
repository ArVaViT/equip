import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Award, CheckCircle, XCircle, Clock } from "lucide-react"
import type { Certificate } from "@/types"
import { formatDate } from "@/i18n/format"

export type AdminCert = Certificate & {
  student_name?: string
  course_title?: string
  approved_by_name?: string
  approved_at?: string
}

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
        <div className="space-y-2">
          {certs.map((cert) => (
            <div
              key={cert.id}
              className="flex flex-col gap-3 rounded-md border border-l-stripe border-l-primary/60 bg-primary/5 p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">
                  {cert.student_name || t("admin.pendingCerts.studentFallback")}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {cert.course_title || t("admin.pendingCerts.courseFallback")}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground/80">
                  {cert.approved_by_name && (
                    <span className="flex items-center gap-1">
                      <CheckCircle className="h-3 w-3 text-success" strokeWidth={1.75} aria-hidden />
                      {t("admin.pendingCerts.approvedBy", { name: cert.approved_by_name })}
                    </span>
                  )}
                  {cert.approved_at && (
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden />
                      {formatDate(cert.approved_at)}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2 sm:ml-4">
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
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
