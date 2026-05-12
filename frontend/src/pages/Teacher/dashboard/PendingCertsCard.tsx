import { Award, CheckCircle, Clock, XCircle } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { PendingCert } from "./types"
import { formatDate } from "@/i18n/format"

interface Props {
  certs: PendingCert[]
  actionId: string | null
  onApprove: (id: string) => void
  onReject: (id: string) => void
}

export function PendingCertsCard({ certs, actionId, onApprove, onReject }: Props) {
  const { t } = useTranslation()
  if (certs.length === 0) return null
  return (
    <Card className="mb-8 border-l-[3px] border-l-warning">
      <CardHeader>
        <CardTitle className="text-xl flex items-center gap-2">
          <Award className="h-5 w-5 text-warning" />
          {t("teacherDashboard.pendingCerts.title")}
          <Badge variant="warning" className="font-normal">
            {certs.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {certs.map((cert) => (
            <div
              key={cert.id}
              className="flex items-center justify-between rounded-md border border-l-[3px] border-l-warning/60 bg-warning/5 p-4"
            >
              <div className="min-w-0">
                <p className="font-medium truncate">
                  {cert.student_name || t("teacherDashboard.pendingCerts.studentFallback")}
                </p>
                <p className="text-sm text-muted-foreground truncate">
                  {cert.course_title || t("teacherDashboard.pendingCerts.courseFallback")}
                </p>
                <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                  <Clock className="h-3 w-3" />
                  {cert.requested_at
                    ? t("teacherDashboard.pendingCerts.requestedPrefix", {
                        date: formatDate(cert.requested_at),
                      })
                    : t("teacherDashboard.pendingCerts.requestedUnknown")}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-4">
                <Button
                  size="sm"
                  onClick={() => onApprove(cert.id)}
                  disabled={actionId === cert.id}
                >
                  <CheckCircle className="h-4 w-4 mr-1.5" />
                  {t("teacherDashboard.pendingCerts.approve")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onReject(cert.id)}
                  disabled={actionId === cert.id}
                  className="text-destructive hover:text-destructive"
                >
                  <XCircle className="h-4 w-4 mr-1.5" />
                  {t("teacherDashboard.pendingCerts.reject")}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
