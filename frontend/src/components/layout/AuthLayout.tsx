import { BookOpen } from "lucide-react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { useTheme } from "@/context/useTheme"
import { Button } from "@/components/ui/button"
import { Moon, Sun } from "lucide-react"

interface AuthLayoutProps {
  children: React.ReactNode
  heading: string
  subheading?: string
}

export default function AuthLayout({ children, heading, subheading }: AuthLayoutProps) {
  const { theme, toggleTheme } = useTheme()
  const { t } = useTranslation()
  const year = new Date().getFullYear()

  return (
    <div className="flex min-h-screen">
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
      <div className="relative hidden bg-card lg:flex lg:w-[480px] xl:w-[560px]">
        <div className="relative z-10 flex flex-col justify-between p-12 text-ink">
          <Link
            to="/"
            className="font-serif text-xl font-semibold tracking-[-0.01em] decoration-transparent underline-offset-4 transition-[text-decoration-color] duration-base hover:underline hover:decoration-ink/30"
          >
            {t("common.appName")}
          </Link>

          <div>
            <div className="h-px w-12 bg-border" />
            <blockquote className="mt-8 font-serif text-2xl font-normal italic leading-snug">
              {t("auth.marketingQuote")}
            </blockquote>
            <p className="mt-5 text-xs uppercase tracking-[0.22em] text-ink-muted">
              {t("auth.marketingReference")}
            </p>
          </div>

          <p className="text-xs text-ink-muted">
            {t("auth.marketingPanelFooter", { year, appName: t("common.appName") })}
          </p>
        </div>
      </div>

      {/* Form panel */}
      <div className="flex flex-1 flex-col">
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

        <div className="flex flex-1 items-center justify-center px-4 py-8 sm:px-8">
          <div className="w-full max-w-[420px] space-y-8">
            <div className="space-y-2 text-center lg:text-left">
              <h1 className="font-serif text-2xl font-bold tracking-tight sm:text-3xl">{heading}</h1>
              {subheading && <p className="font-sans text-sm text-ink-muted">{subheading}</p>}
            </div>
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
