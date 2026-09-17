import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react"
import { useTranslation } from "react-i18next"
import { Link, useLocation } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { legalService } from "@/services/legal"
import { useAuth } from "@/context/useAuth"
import { getFirstRunActive, subscribeFirstRun } from "@/lib/tourState"
import { DEFAULT_LOCALE, isSupportedLocale } from "@/i18n/config"
import { toast } from "@/lib/toast"
import { useTeacherAgreement } from "./useTeacherAgreement"

/** Same definition the first-run flow uses. Kept local rather than exported
 *  from there, because the two gates are allowed to diverge. */
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * The screen somebody meets the moment they become a teacher.
 *
 * It is a congratulation and a gate in the same breath, and that is
 * deliberate: the platform has just handed this person the ability to publish
 * material to other people, read other people's work and decide what a
 * certificate says. Each of those is a responsibility the Teacher & Contributor
 * Agreement spells out, and the moment to read it is the moment it starts
 * applying — not the first time something goes wrong.
 *
 * Blocking, with three things that keep it from being a trap:
 *
 * - **the checkbox starts empty** and Continue stays disabled until it is
 *   ticked. Nothing is pre-agreed on somebody's behalf;
 * - **the full text is one click away**, opening in a new tab, and is public —
 *   readable before the checkbox, by anybody, signed in or not;
 * - **signing out is visible on the screen**. A window somebody cannot leave
 *   must not also hide the door.
 *
 * It does not render while the first-run consent gate is up. Both would
 * otherwise appear at once for a teacher meeting the platform for the first
 * time, and being asked to celebrate before being asked to consent is the
 * wrong order.
 */
export function TeacherAgreementGate() {
  const { user, logout, refreshUser } = useAuth()
  const { t, i18n } = useTranslation()
  const { pathname } = useLocation()
  const locale = isSupportedLocale(i18n.language) ? i18n.language : DEFAULT_LOCALE
  const { owed, onAccepted } = useTeacherAgreement(user?.id)
  const [checked, setChecked] = useState(false)
  const [saving, setSaving] = useState(false)
  const checkboxId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)

  // Same reasoning as the first-run gate: this component mounts on every
  // route, so a link out of it to the document would open a tab where it
  // mounts again and covers the text somebody was sent to read.
  const exempt = pathname === "/teacher-terms" || pathname === "/terms" || pathname === "/privacy"

  const firstRunActive = useSyncExternalStore(subscribeFirstRun, getFirstRunActive, getFirstRunActive)

  const open = Boolean(owed) && !exempt && !firstRunActive

  useEffect(() => {
    if (!open) return
    const root = dialogRef.current
    if (!root) return
    const id = window.requestAnimationFrame(() => {
      if (root.contains(document.activeElement)) return
      root.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus()
    })
    return () => window.cancelAnimationFrame(id)
  }, [open])

  // Escape must not close a gate, and Tab must not walk out of it into the
  // page underneath — which is still rendered, just covered.
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        e.stopPropagation()
        return
      }
      if (e.key !== "Tab") return
      const root = dialogRef.current
      if (!root) return
      const focusables = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      )
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (!first || !last) return
      const active = document.activeElement as HTMLElement | null
      if (e.shiftKey && (active === first || !root.contains(active))) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener("keydown", handler, true)
    return () => document.removeEventListener("keydown", handler, true)
  }, [open])

  if (!open || !owed) return null

  const confirm = async () => {
    setSaving(true)
    try {
      await legalService.accept(owed.slug, owed.version, locale)
      onAccepted()
      // The role that produced this gate is the one the client has not seen
      // yet. Now is the moment to go and get it, so the teacher menu and the
      // /teacher routes are there when the screen closes.
      await refreshUser()
    } catch {
      toast({ title: t("legalGate.teacher.saveFailed"), variant: "destructive" })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="teacher-agreement-heading"
      className="fixed inset-0 z-[2147483645] flex items-start justify-center overflow-y-auto bg-surface px-4 py-10 sm:items-center sm:py-16"
    >
      <div className="flex w-full max-w-xl flex-col items-center gap-5 text-center">
        <span className="block h-px w-12 bg-accent/60" aria-hidden />
        <p className="text-xs font-medium uppercase tracking-[0.22em] text-accent">
          {t("legalGate.teacher.eyebrow")}
        </p>
        <h1
          id="teacher-agreement-heading"
          className="font-serif text-2xl font-semibold leading-tight tracking-tight text-ink sm:text-3xl"
        >
          {t("legalGate.teacher.title")}
        </h1>
        <p className="max-w-md text-sm leading-relaxed text-ink-muted sm:text-base">
          {t("legalGate.teacher.intro")}
        </p>

        <ul className="mt-2 w-full space-y-3 text-left text-sm leading-relaxed text-ink-muted">
          <li className="flex gap-3 rounded-md bg-muted/20 p-3">
            <span aria-hidden className="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
            <span>{t("legalGate.teacher.bullets.rights")}</span>
          </li>
          <li className="flex gap-3 rounded-md bg-muted/20 p-3">
            <span aria-hidden className="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
            <span>{t("legalGate.teacher.bullets.students")}</span>
          </li>
          <li className="flex gap-3 rounded-md bg-muted/20 p-3">
            <span aria-hidden className="mt-1.5 block h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
            <span>{t("legalGate.teacher.bullets.marks")}</span>
          </li>
        </ul>

        <div className="mt-2 flex w-full items-start gap-3 rounded-md bg-surface p-3 text-left">
          <Checkbox
            id={checkboxId}
            checked={checked}
            onCheckedChange={(v) => setChecked(v === true)}
            className="mt-0.5"
          />
          <label htmlFor={checkboxId} className="cursor-pointer text-sm leading-snug text-ink">
            {t("legalGate.teacher.checkbox")}
          </label>
        </div>

        <p className="text-sm text-ink-muted">
          <Link to="/teacher-terms" target="_blank" className="text-brand underline-offset-4 hover:underline">
            {t("legal.teacherTerms")}
          </Link>
        </p>

        <Button
          type="button"
          onClick={confirm}
          disabled={!checked || saving}
          size="lg"
          className="w-full sm:w-auto sm:min-w-[160px]"
        >
          {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" strokeWidth={1.75} aria-hidden />}
          {t("legalGate.teacher.next")}
        </Button>

        {/* The door. A screen somebody cannot dismiss must not also be a screen
            they cannot walk away from — that is the difference between a gate
            and a hostage situation, and it costs one line. */}
        <button
          type="button"
          onClick={() => void logout()}
          className="text-xs text-ink-muted underline-offset-4 hover:text-ink hover:underline"
        >
          {t("legalGate.signOut")}
        </button>
      </div>
    </div>
  )
}
