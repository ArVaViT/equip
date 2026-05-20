import { useId, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"

interface Props {
  onAccept: () => void
}

/**
 * First-run Step 1 — Privacy Policy gate.
 *
 * Editorial composition matching the rest of the onboarding voice:
 * thin sage rule → eyebrow → Fraunces serif title → warm paragraph →
 * three short bullets → checkbox → single primary CTA.
 *
 * No skip path. The user MUST accept before continuing — this is the
 * legal gate, not a settings screen. Closing the browser without
 * accepting leaves nothing persisted, so the gate fires again next
 * visit.
 */
export function PrivacyPolicyStep({ onAccept }: Props) {
  const { t } = useTranslation()
  const [accepted, setAccepted] = useState(false)
  const checkboxId = useId()

  return (
    <div className="flex w-full max-w-xl flex-col items-center gap-5 text-center">
      <span className="block h-px w-12 bg-accent/60" aria-hidden />
      <p className="text-[11px] font-medium uppercase tracking-[0.22em] text-accent">
        {t("firstRun.privacy.eyebrow")}
      </p>
      <h1 className="font-serif text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-3xl">
        {t("firstRun.privacy.title")}
      </h1>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground sm:text-base">
        {t("firstRun.privacy.intro")}
      </p>

      <ul className="mt-2 w-full space-y-3 text-left text-sm leading-relaxed text-muted-foreground">
        <li className="flex gap-3 rounded-md border border-border/60 bg-muted/20 p-3">
          <span aria-hidden className="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
          <span>{t("firstRun.privacy.bullets.collect")}</span>
        </li>
        <li className="flex gap-3 rounded-md border border-border/60 bg-muted/20 p-3">
          <span aria-hidden className="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
          <span>{t("firstRun.privacy.bullets.share")}</span>
        </li>
        <li className="flex gap-3 rounded-md border border-border/60 bg-muted/20 p-3">
          <span aria-hidden className="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
          <span>{t("firstRun.privacy.bullets.control")}</span>
        </li>
      </ul>

      <div className="mt-2 flex w-full items-start gap-3 rounded-md border border-border bg-background p-3 text-left">
        <Checkbox
          id={checkboxId}
          checked={accepted}
          onCheckedChange={(v) => setAccepted(v === true)}
          className="mt-0.5"
        />
        <label
          htmlFor={checkboxId}
          className="cursor-pointer text-sm leading-snug text-foreground"
        >
          {t("firstRun.privacy.checkbox")}
        </label>
      </div>

      <Button
        type="button"
        onClick={onAccept}
        disabled={!accepted}
        size="lg"
        className="w-full sm:w-auto sm:min-w-[160px]"
      >
        {t("firstRun.privacy.next")}
      </Button>
    </div>
  )
}
