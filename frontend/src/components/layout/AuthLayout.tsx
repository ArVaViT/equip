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
      {/* Marketing column — tokens from index.css */}
      <div className="relative hidden overflow-hidden bg-[hsl(var(--auth-panel-bg))] lg:flex lg:w-[480px] xl:w-[560px]">
        <div className="absolute inset-0">
          <div className="absolute -left-10 top-20 h-72 w-72 rounded-full bg-[hsl(var(--auth-panel-glow-warm)/0.08)] blur-3xl" />
          <div className="absolute bottom-32 right-10 h-56 w-56 rounded-full bg-[hsl(var(--auth-panel-glow-warm)/0.06)] blur-2xl" />
        </div>

        <div className="relative z-10 flex flex-col justify-between p-10 text-[hsl(var(--auth-panel-text)/0.92)]">
          <Link to="/" className="flex items-center gap-2.5 transition-opacity hover:opacity-85">
            <BookOpen
              className="h-6 w-6 shrink-0 text-[hsl(var(--auth-panel-accent-line)/0.95)]"
              strokeWidth={1.75}
              aria-hidden
            />
            <span className="font-serif text-xl font-bold tracking-tight">{t("common.appName")}</span>
          </Link>

          <div className="space-y-8">
            <div className="h-px w-12 bg-[hsl(var(--auth-panel-accent-line)/0.35)]" />
            <blockquote className="font-serif text-2xl font-normal italic leading-relaxed text-[hsl(var(--auth-panel-text)/0.88)]">
              {t("auth.marketingQuote")}
            </blockquote>
            <div className="flex items-center gap-3">
              <div className="h-px flex-1 bg-[hsl(var(--auth-panel-text)/0.12)]" />
              <span className="font-sans text-xs uppercase tracking-widest text-[hsl(var(--auth-panel-text-muted))]">
                {t("auth.marketingReference")}
              </span>
              <div className="h-px flex-1 bg-[hsl(var(--auth-panel-text)/0.12)]" />
            </div>
          </div>

          <p className="font-sans text-xs text-[hsl(var(--auth-panel-text)/0.38)]">
            {t("auth.marketingPanelFooter", { year, appName: t("common.appName") })}
          </p>
        </div>
      </div>

      {/* Form panel */}
      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-border/60 bg-background/90 px-4 py-2 backdrop-blur-sm lg:hidden">
          <Link
            to="/"
            className="-mx-1 inline-flex min-h-[44px] items-center gap-2.5 px-1 text-foreground transition-opacity hover:opacity-80"
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
              {subheading && <p className="font-sans text-sm text-muted-foreground">{subheading}</p>}
            </div>
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
