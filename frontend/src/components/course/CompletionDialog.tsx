import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Sparkles } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { coursesService } from "@/services/courses"
import { toast } from "@/lib/toast"
import type { Certificate } from "@/types"

interface Props {
  open: boolean
  onClose: () => void
  courseId: string
  courseTitle: string
  /** Whether the student already has a certificate record on file for
   *  this course (any status). When ``true``, the dialog drops the
   *  "Request" CTA — the request is already in flight — and leans the
   *  body copy on the cert card sitting just below on the page. */
  hasCertificate: boolean
  /** Forwarded to the cert state once a new request lands so the
   *  ``<CertificateCard>`` repaints into the pending state without
   *  needing a parent refetch. */
  onCertificateRequested: (cert: Certificate) => void
}

/**
 * Celebration dialog shown when a student reaches 100% progress on a
 * course for the first time on this device.
 *
 * Composition: sage rule → eyebrow → Fraunces serif title → one
 * paragraph of warm body → one or two CTAs. Visual voice matches the
 * ``<WelcomeCard>`` first-time moment so completion and onboarding
 * share the same hand-set editorial register — no confetti, no
 * star-burst, no badge swarm.
 *
 * Dismissal is fire-and-forget: closing the dialog (X, overlay click,
 * Escape, or either CTA) writes a per-course flag to localStorage so
 * the moment never re-fires on the same device. Trigger logic lives
 * in ``EnrolledView`` — this component is presentation only.
 */
export default function CompletionDialog({
  open,
  onClose,
  courseId,
  courseTitle,
  hasCertificate,
  onCertificateRequested,
}: Props) {
  const { t } = useTranslation()
  const [requesting, setRequesting] = useState(false)

  const handleRequest = async () => {
    setRequesting(true)
    try {
      const cert = await coursesService.requestCertificate(courseId)
      onCertificateRequested(cert)
      toast({ title: t("certificates.card.requestSuccess"), variant: "success" })
      onClose()
    } catch {
      toast({ title: t("certificates.card.requestFailed"), variant: "destructive" })
    } finally {
      setRequesting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
    >
      <DialogContent className="sm:max-w-md">
        <div className="flex flex-col items-center gap-4 pt-2 text-center">
          <span className="block h-px w-12 bg-accent/60" aria-hidden />
          <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.22em] text-accent">
            <Sparkles className="h-3 w-3" strokeWidth={1.75} aria-hidden />
            {t("completion.eyebrow")}
          </p>
          {/* Radix-required accessible title doubles as the visible
              serif headline — overriding the default text-lg/sans
              styles with the editorial vocabulary used on
              ``<WelcomeCard>`` so the two first-time moments share a
              voice. */}
          <DialogTitle className="max-w-md text-balance font-serif text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-3xl">
            {t("completion.title", { courseTitle })}
          </DialogTitle>
          <p className="max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base">
            {hasCertificate ? t("completion.bodyHasCert") : t("completion.body")}
          </p>
          <div className="flex flex-col gap-2 pt-2 sm:flex-row">
            {!hasCertificate && (
              <Button onClick={handleRequest} disabled={requesting}>
                <Sparkles className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
                {requesting
                  ? t("certificates.card.requesting")
                  : t("completion.requestCta")}
              </Button>
            )}
            <Button variant="outline" onClick={onClose} disabled={requesting}>
              {t("completion.continueCta")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
