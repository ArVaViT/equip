import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Globe2,
  Layers,
  ShieldCheck,
} from "lucide-react"
import { Button } from "@/components/ui/button"

/**
 * Marketing landing rendered at ``/`` for unauthenticated visitors.
 *
 * Three goals:
 *
 * 1. **Activation.** First-time visitors should reach either the
 *    catalog (browse → enroll) or registration in one click. Two
 *    primary CTAs sit above the fold; a third "ready to start" CTA
 *    closes the page.
 *
 * 2. **SEO surface.** Sections introduce real internal links to
 *    ``/courses``, ``/register``, ``/login``, ``/forgot-password``.
 *    Real ``<Link>`` elements (not button-look-alikes wired to
 *    ``navigate()``) keep them crawler-visible without JS. The
 *    feature grid + "how it works" steps add semantic content for
 *    crawlers and feed Google's sitelinks heuristic with named
 *    sections.
 *
 * 3. **Trust signals.** The "for whom" + "what's inside" copy makes
 *    the platform's positioning explicit ("системное изучение",
 *    "сертификаты", "двуязычность") instead of leaving it to the
 *    one-line tagline.
 *
 * Russian-first by default (matches ``DEFAULT_LOCALE``). i18n keys
 * live under ``landing.*``; English translations mirror the structure
 * so a returning EN viewer sees the same sections.
 */
export function PublicLanding() {
  const { t } = useTranslation()
  return (
    <div className="container mx-auto max-w-5xl px-4 pb-24">
      {/* ── Hero ────────────────────────────────────────────────── */}
      <section className="flex flex-col items-center pt-16 text-center sm:pt-24">
        <h1 className="font-serif text-4xl font-bold tracking-tight text-foreground sm:text-5xl md:text-6xl">
          {t("common.appName")}
        </h1>
        <p className="mt-4 max-w-2xl text-balance text-base leading-relaxed text-muted-foreground sm:text-lg">
          {t("footer.tagline")}
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link to="/courses">
            <Button size="lg">
              {t("dashboard.browseAllCta")}
              <ArrowRight className="ml-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            </Button>
          </Link>
          <Link to="/register">
            <Button size="lg" variant="outline">
              {t("landing.hero.registerCta")}
            </Button>
          </Link>
          <Link to="/login">
            <Button size="lg" variant="ghost">
              {t("common.signIn")}
            </Button>
          </Link>
        </div>
      </section>

      {/* ── Features grid ───────────────────────────────────────── */}
      <section
        aria-labelledby="landing-features-heading"
        className="mt-20 sm:mt-28"
      >
        <h2
          id="landing-features-heading"
          className="font-serif text-2xl font-semibold tracking-tight sm:text-3xl"
        >
          {t("landing.features.heading")}
        </h2>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          {t("landing.features.subheading")}
        </p>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <FeatureCard
            icon={<Layers className="h-5 w-5" strokeWidth={1.75} aria-hidden />}
            title={t("landing.features.systematic.title")}
            body={t("landing.features.systematic.body")}
          />
          <FeatureCard
            icon={<CheckCircle2 className="h-5 w-5" strokeWidth={1.75} aria-hidden />}
            title={t("landing.features.progress.title")}
            body={t("landing.features.progress.body")}
          />
          <FeatureCard
            icon={<ShieldCheck className="h-5 w-5" strokeWidth={1.75} aria-hidden />}
            title={t("landing.features.certificates.title")}
            body={t("landing.features.certificates.body")}
          />
          <FeatureCard
            icon={<Globe2 className="h-5 w-5" strokeWidth={1.75} aria-hidden />}
            title={t("landing.features.bilingual.title")}
            body={t("landing.features.bilingual.body")}
          />
        </div>
      </section>

      {/* ── How it works ────────────────────────────────────────── */}
      <section
        aria-labelledby="landing-how-heading"
        className="mt-20 rounded-lg border bg-muted/30 px-6 py-10 sm:mt-28 sm:px-10 sm:py-12"
      >
        <h2
          id="landing-how-heading"
          className="font-serif text-2xl font-semibold tracking-tight sm:text-3xl"
        >
          {t("landing.how.heading")}
        </h2>
        <ol className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-3">
          <Step n={1} text={t("landing.how.step1")} />
          <Step n={2} text={t("landing.how.step2")} />
          <Step n={3} text={t("landing.how.step3")} />
        </ol>
      </section>

      {/* ── Quick links — internal-linking section for sitelinks ─── */}
      <section
        aria-labelledby="landing-quicklinks-heading"
        className="mt-20 sm:mt-28"
      >
        <h2
          id="landing-quicklinks-heading"
          className="font-serif text-2xl font-semibold tracking-tight sm:text-3xl"
        >
          {t("landing.quicklinks.heading")}
        </h2>
        <ul className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <QuickLink
            to="/courses"
            icon={<BookOpen className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
            title={t("landing.quicklinks.catalog.title")}
            body={t("landing.quicklinks.catalog.body")}
          />
          <QuickLink
            to="/register"
            icon={<ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
            title={t("landing.quicklinks.register.title")}
            body={t("landing.quicklinks.register.body")}
          />
          <QuickLink
            to="/login"
            icon={<ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
            title={t("landing.quicklinks.signIn.title")}
            body={t("landing.quicklinks.signIn.body")}
          />
          <QuickLink
            to="/forgot-password"
            icon={<ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden />}
            title={t("landing.quicklinks.forgot.title")}
            body={t("landing.quicklinks.forgot.body")}
          />
        </ul>
      </section>

      {/* ── Final CTA ───────────────────────────────────────────── */}
      <section className="mt-20 flex flex-col items-center text-center sm:mt-28">
        <h2 className="font-serif text-2xl font-semibold tracking-tight sm:text-3xl">
          {t("landing.finalCta.heading")}
        </h2>
        <p className="mt-3 max-w-xl text-balance text-sm text-muted-foreground sm:text-base">
          {t("landing.finalCta.body")}
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link to="/register">
            <Button size="lg">
              {t("landing.finalCta.primary")}
              <ArrowRight className="ml-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            </Button>
          </Link>
          <Link to="/courses">
            <Button size="lg" variant="outline">
              {t("dashboard.browseAllCta")}
            </Button>
          </Link>
        </div>
      </section>
    </div>
  )
}

interface FeatureCardProps {
  icon: React.ReactNode
  title: string
  body: string
}

function FeatureCard({ icon, title, body }: FeatureCardProps) {
  return (
    <div className="flex flex-col rounded-lg border bg-card p-5">
      <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
        {icon}
      </span>
      <h3 className="mt-4 text-base font-semibold text-foreground">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{body}</p>
    </div>
  )
}

interface StepProps {
  n: number
  text: string
}

function Step({ n, text }: StepProps) {
  return (
    <li className="flex items-start gap-3">
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
        {n}
      </span>
      <p className="pt-0.5 text-sm leading-relaxed text-foreground">{text}</p>
    </li>
  )
}

interface QuickLinkProps {
  to: string
  icon: React.ReactNode
  title: string
  body: string
}

function QuickLink({ to, icon, title, body }: QuickLinkProps) {
  return (
    <li>
      <Link
        to={to}
        className="group flex items-start gap-3 rounded-md border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">
          {icon}
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-medium text-foreground">{title}</span>
          <span className="mt-0.5 block text-xs text-muted-foreground">{body}</span>
        </span>
      </Link>
    </li>
  )
}
