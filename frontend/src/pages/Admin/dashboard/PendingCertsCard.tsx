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
  if (certs.length === 0) return null

  return (
    <Card className="mb-8 border-l-[3px] border-l-primary">
      <CardHeader>
        <CardTitle className="text-xl flex items-center gap-2">
          <Award className="h-5 w-5 text-primary" strokeWidth={1.75} aria-hidden />
          Certificate Approvals
          <Badge variant="default" className="font-normal">
            {certs.length}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {certs.map((cert) => (
            <div
              key={cert.id}
              className="flex items-center justify-between rounded-md border border-l-[3px] border-l-primary/60 bg-primary/5 p-4"
            >
              <div className="min-w-0">
                <p className="font-medium truncate">{cert.student_name || "Student"}</p>
                <p className="text-sm text-muted-foreground truncate">
                  {cert.course_title || "Course"}
                </p>
                <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                  {cert.approved_by_name && (
                    <span className="flex items-center gap-1">
                      <CheckCircle className="h-3.5 w-3.5 text-success" strokeWidth={1.75} aria-hidden />
                      Approved by {cert.approved_by_name}
                    </span>
                  )}
                  {cert.approved_at && (
                    <span className="flex items-center gap-1">
                      <Clock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
                      {formatDate(cert.approved_at)}
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0 ml-4">
                <Button
                  size="sm"
                  onClick={() => onApprove(cert.id)}
                  disabled={actionId === cert.id}
                >
                  <CheckCircle className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                  Approve
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onReject(cert.id)}
                  disabled={actionId === cert.id}
                  className="text-destructive hover:text-destructive"
                >
                  <XCircle className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                  Reject
                </Button>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
