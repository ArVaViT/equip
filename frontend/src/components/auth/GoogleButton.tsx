import { useTranslation } from "react-i18next"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { GoogleIcon } from "./GoogleIcon"
import { isInAppBrowser } from "@/lib/inAppBrowser"

interface Props {
  loading: boolean
  disabled?: boolean
  onClick: () => void
}

/**
 * «Continue with Google», the same on every screen that offers it.
 *
 * Inside another app's built-in browser Google refuses the sign-in outright,
 * so there the button says, in one line under it, where it will work.
 */
export function GoogleButton({ loading, disabled, onClick }: Props) {
  const { t } = useTranslation()
  const inApp = isInAppBrowser()
  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="outline"
        size="lg"
        className="w-full font-medium rounded-md"
        onClick={onClick}
        disabled={loading || disabled}
        aria-describedby={inApp ? "google-in-app-hint" : undefined}
      >
        {loading ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" strokeWidth={1.75} />
            {t("auth.connecting")}
          </>
        ) : (
          <>
            <GoogleIcon className="h-4 w-4 mr-2.5" />
            {t("auth.continueWithGoogle")}
          </>
        )}
      </Button>
      {inApp && (
        <p id="google-in-app-hint" className="text-center text-xs text-ink-muted">
          {t("auth.googleInAppBrowser")}
        </p>
      )}
    </div>
  )
}

/** «or …» between the Google button and the email form. */
export function OrDivider({ label }: { label: string }) {
  // Two rules either side of the words, not one rule under a patch of page
  // colour: the patch showed as a box once the sign-in screens got the
  // landing's scene behind them.
  return (
    <div className="flex items-center gap-3 text-xs uppercase text-ink-muted">
      <div className="h-px flex-1 bg-border" />
      <span>{label}</span>
      <div className="h-px flex-1 bg-border" />
    </div>
  )
}
