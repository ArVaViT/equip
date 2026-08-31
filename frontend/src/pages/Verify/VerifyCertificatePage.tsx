import { useCallback, useEffect, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { BadgeCheck, Search, ShieldX } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ErrorState, PageHeader } from "@/components/patterns"
import { certificatesService, type CertificateVerification } from "@/services/certificates"
import { formatDateLong } from "@/i18n/format"

/**
 * Checking a certificate by the number printed on it.
 *
 * The backend has answered `GET /certificates/verify/{number}` without
 * authentication since certificates existed; the certificate document prints
 * "Verify at equipbible.com/verify/<number>"; the landing page advertises
 * "verifiable certificates". There was no such page. Every certificate this
 * platform has ever issued carries an address that returns 404 — checked in
 * production on 2026-08-31 against a real number.
 *
 * Deliberately outside `<Gate>`: the reader is an employer, a pastor or
 * another school. Requiring them to sign up to check somebody else's
 * credential would defeat the purpose of printing the address at all.
 */
export default function VerifyCertificatePage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { certificateNumber } = useParams<{ certificateNumber: string }>()
  const [input, setInput] = useState(certificateNumber ?? "")
  const [result, setResult] = useState<CertificateVerification | null>(null)
  const [checking, setChecking] = useState(false)
  const [failed, setFailed] = useState(false)

  const check = useCallback(async (number: string) => {
    setChecking(true)
    setFailed(false)
    try {
      setResult(await certificatesService.verifyCertificate(number))
    } catch {
      // A network or server failure is NOT "this certificate is fake" — the
      // two must never look alike on a page whose whole job is to be trusted.
      setResult(null)
      setFailed(true)
    } finally {
      setChecking(false)
    }
  }, [])

  useEffect(() => {
    if (!certificateNumber) {
      setResult(null)
      return
    }
    setInput(certificateNumber)
    void check(certificateNumber)
  }, [certificateNumber, check])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = input.trim()
    if (!trimmed) return
    navigate(`/verify/${encodeURIComponent(trimmed)}`)
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-10 sm:px-6">
      <PageHeader eyebrow={t("verify.eyebrow")} title={t("verify.title")} description={t("verify.subtitle")} />

      <form onSubmit={submit} className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1 space-y-2">
          <Label htmlFor="certificate-number">{t("verify.numberLabel")}</Label>
          <Input
            id="certificate-number"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t("verify.placeholder")}
            fieldSize="lg"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <Button type="submit" size="lg" disabled={checking || !input.trim()} className="shrink-0">
          <Search className="mr-2 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {checking ? t("verify.checking") : t("verify.submit")}
        </Button>
      </form>

      <div className="mt-8" aria-live="polite">
        {failed && (
          <ErrorState
            title={t("verify.errorTitle")}
            description={t("verify.errorDescription")}
            action={
              certificateNumber ? (
                <Button variant="outline" onClick={() => void check(certificateNumber)}>
                  {t("common.tryAgain")}
                </Button>
              ) : undefined
            }
          />
        )}

        {result?.valid && (
          <Card className="border-l-stripe border-l-accent">
            <CardContent className="space-y-5 px-6 py-6">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-md bg-success/10">
                  <BadgeCheck className="h-5 w-5 text-success-ink" strokeWidth={1.75} aria-hidden />
                </div>
                <p className="font-serif text-lg font-semibold text-ink">{t("verify.validHeading")}</p>
              </div>

              <dl className="space-y-3 border-t border-edge pt-4 text-sm">
                <div>
                  <dt className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                    {t("verify.issuedTo")}
                  </dt>
                  <dd className="mt-1 font-medium text-ink">{result.user_name}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                    {t("verify.courseLabel")}
                  </dt>
                  <dd className="mt-1 text-ink">{result.course_title}</dd>
                </div>
                {result.issued_at && (
                  <div>
                    <dt className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                      {t("verify.issuedAt")}
                    </dt>
                    <dd className="mt-1 text-ink">{formatDateLong(result.issued_at)}</dd>
                  </div>
                )}
                <div>
                  <dt className="text-xs font-medium uppercase tracking-[0.18em] text-ink-muted">
                    {t("verify.numberLabel")}
                  </dt>
                  <dd className="mt-1 font-mono text-ink">{result.certificate_number}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        )}

        {result && !result.valid && (
          <Card className="border-l-stripe border-l-muted-foreground/30">
            <CardContent className="space-y-3 px-6 py-6">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-md bg-muted">
                  <ShieldX className="h-5 w-5 text-ink-muted" strokeWidth={1.75} aria-hidden />
                </div>
                <p className="font-serif text-lg font-semibold text-ink">{t("verify.invalidHeading")}</p>
              </div>
              {/* Says nothing about anybody: an unknown number must not
                  become a way to probe who studied here. */}
              <p className="text-sm text-ink-muted">
                {t("verify.invalidDescription", { number: result.certificate_number })}
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
