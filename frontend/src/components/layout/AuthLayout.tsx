import { lazy, Suspense, useEffect, useState } from "react"
import { BookOpen } from "lucide-react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { useReducedMotion } from "motion/react"
import { useTheme } from "@/context/useTheme"
import { Button } from "@/components/ui/button"
import { Moon, Sun } from "lucide-react"

// The landing's text veil (`landing/textVeil.ts`), held solid further out:
// the form's quiet lines — the subheading, the divider, «Нет аккаунта?» —
// sit near its edge, and the landing's stops let the drifting leaves take
// them to 4.4:1 on a desktop (measured 2026-09-28, three moments each, both
// themes). On a phone the veil is at 70%: the form fills the screen there,
// and a full veil cleared the scene off it entirely.
const FORM_VEIL =
  "relative isolate before:pointer-events-none before:absolute before:-inset-x-32 before:-inset-y-36 before:-z-10 before:content-[''] before:bg-[radial-gradient(closest-side,hsl(var(--background))_62%,hsl(var(--background)/0.92)_74%,hsl(var(--background)/0.6)_85%,hsl(var(--background)/0.2)_94%,hsl(var(--background)/0))] max-lg:before:opacity-70"

// The landing's scene, lazily: `three` reaches the sign-in screens only
// after the form has rendered, and never where motion is unwelcome.
const LandingBackdrop = lazy(() => import("@/pages/Dashboard/landing/LandingBackdrop"))

interface AuthLayoutProps {
  children: React.ReactNode
  heading: string
  subheading?: string
}

export default function AuthLayout({ children, heading, subheading }: AuthLayoutProps) {
  const { theme, toggleTheme } = useTheme()
  const { t } = useTranslation()
  const prefersReducedMotion = useReducedMotion()
  // `matchMedia` doubles as "is this a real browser": jsdom has neither it
  // nor WebGL. Same fence as the landing.
  const [canAnimate, setCanAnimate] = useState(false)
  useEffect(() => {
    if (typeof window.matchMedia === "function") setCanAnimate(true)
  }, [])

  return (
    // `overflow-clip`: the veil behind the form reaches 128px past it and
    // widened a phone's document to 502px (as on the landing, where the
    // same cure is explained).
    <div className="relative flex min-h-screen overflow-clip">
      {/* The landing's leaves, continued onto the door into the product —
          «фоновую анимацию похожую на ту что у нас в лендинге». One fixed
          canvas behind both panels, above their paper and below their
          words: the panels' own text sits on `z-10`. `ambient`, because
          nothing scrolls here — see `LandingBackdrop`. */}
      {canAnimate && !prefersReducedMotion && (
        <Suspense fallback={null}>
          <LandingBackdrop ambient className="pointer-events-none fixed inset-0 z-[5]" />
        </Suspense>
      )}
      {/* The title page.
       *
       * This was a violet panel with two blurred glow circles — a second
       * accent, a decorative gradient and 288px of blur, which is three of the
       * five things the art direction forbids, on the first screen anybody
       * sees, in the violet everything else was moved away from. It was also
       * `lg:` only, so the student on a mid-range Android never saw it and the
       * director on a desktop saw a login page from a different design system.
       *
       * The instinct was right: a verse in the serif is exactly the register.
       * What it needed was paper and ink instead of glow — set as the title
       * page of a book, with the rule doing the work the gradient was doing. */}
      <aside className="relative hidden bg-card lg:flex lg:w-[480px] xl:w-[560px]">
        <div className="relative z-10 flex flex-col p-12 text-ink">
          <Link
            to="/"
            className="font-serif text-xl font-semibold tracking-[-0.01em] decoration-transparent underline-offset-4 transition-[text-decoration-color] duration-base hover:underline hover:decoration-ink/30"
          >
            {t("common.appName")}
          </Link>

          {/* No colophon under the verse since 2026-09-28: «футер тут не
              нужен». The verse holds the middle of the page on its own. */}
          <div className="my-auto">
            <div className="h-px w-12 bg-border" />
            <blockquote className="mt-8 font-serif text-2xl font-normal italic leading-snug">
              {t("auth.marketingQuote")}
            </blockquote>
            <p className="mt-5 text-xs uppercase tracking-[0.22em] text-ink-muted">
              {t("auth.marketingReference")}
            </p>
          </div>
        </div>
      </aside>

      {/* Form panel */}
      <div className="flex flex-1 flex-col">
        {/* One <header> around both bars: they are the same landmark shown at
            two breakpoints, and two <header> elements would be two banners. */}
        <header className="relative z-10">
          {/* Solid, not blurred: `backdrop-filter` is the most expensive property
              on the phones this product is actually read on. */}
          <div className="flex items-center justify-between bg-card px-4 py-2 lg:hidden">
            <Link
              to="/"
              className="-mx-1 inline-flex min-h-[44px] items-center gap-2.5 px-1 text-ink transition-opacity hover:opacity-80"
            >
              <BookOpen className="h-5 w-5 shrink-0 text-accent" strokeWidth={1.75} aria-hidden />
              <span className="font-serif text-base font-bold leading-none tracking-tight">{t("common.appName")}</span>
            </Link>
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={toggleTheme}
              className="h-11 w-11 shrink-0 rounded-full p-0"
              aria-label={t("auth.toggleColorTheme")}
            >
              {theme === "dark" ? (
                <Sun className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              ) : (
                <Moon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              )}
            </Button>
          </div>

          <div className="hidden justify-end p-4 lg:flex">
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={toggleTheme}
              className="h-9 w-9 rounded-full p-0"
              aria-label={t("auth.toggleColorTheme")}
            >
              {theme === "dark" ? (
                <Sun className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              ) : (
                <Moon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
              )}
            </Button>
          </div>
        </header>

        {/* The auth screens are the first page a visitor sees, and they had
            no <main>: nothing for the skip link to reach, no landmark for a
            screen reader to jump to, and `useFocusMainOnRouteChange` (App.tsx)
            looking up `#main-content` found nothing — so moving between /login
            and /register announced nothing at all. */}
        <main
          id="main-content"
          tabIndex={-1}
          className="relative z-10 flex flex-1 items-center justify-center px-4 py-8 focus:outline-none sm:px-8"
        >
          {/* A clearing in the scene behind the form (`FORM_VEIL` above). */}
          <div className={`w-full max-w-[420px] space-y-8 ${FORM_VEIL}`}>
            <div className="space-y-2 text-center lg:text-left">
              <h1 className="font-serif text-2xl font-bold tracking-tight sm:text-3xl">{heading}</h1>
              {subheading && <p className="font-sans text-sm text-ink-muted">{subheading}</p>}
            </div>
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}
