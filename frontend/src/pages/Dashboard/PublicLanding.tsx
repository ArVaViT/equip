import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  Award,
  BookOpen,
  Check,
  Circle,
  Languages,
  PenLine,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Eyebrow } from "@/components/patterns";
import Footer from "@/components/layout/Footer";
import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from "@/i18n/config";

/**
 * Marketing landing rendered at ``/`` for unauthenticated visitors.
 *
 * Rebuilt 2026-07 to replace the generic shadcn-template feel (a flat
 * 4-icon feature grid + a "Quick links" card grid whose weakest entry
 * was a "Восстановить пароль"/"Reset password" marketing card — real
 * template filler, not something worth landing-page real estate).
 *
 * Structure now:
 *
 * 1. **Hero** — brand, tagline, a qualitative trust strip (no invented
 *    numbers — see feedback-do-not-fabricate-numbers), two primary CTAs.
 * 2. **Value rows** — four alternating narrative rows, each pairing one
 *    concrete claim with a small illustrative UI mock built from the
 *    same tokens/components used elsewhere in the product (not stock
 *    icons + adjectives, and not a screenshot pipeline).
 * 3. **How it works** — unchanged 3-step list.
 * 4. **Final CTA** — single strong close, not a stacked link wall.
 *
 * SEO: crawlable internal links to /courses, /register, /login live in
 * the hero + final CTA (real ``<Link>`` elements, not button-look-alikes
 * wired to ``navigate()``). /forgot-password is intentionally NOT
 * linked from marketing copy — it's one click from /login, which is
 * where a real visitor needs it; giving it a landing-page feature card
 * was the filler tell being fixed here.
 */
export function PublicLanding() {
  const { t } = useTranslation();
  return (
    // The footer lives here now rather than in the app shell — this is the
    // one page it was designed for. The content above keeps the landing
    // page's own measure; the footer spans the full width beneath it.
    <div className="w-full">
      <div className="container mx-auto max-w-5xl px-4">
        {/* ── Hero ────────────────────────────────────────────────── */}
        <section className="relative" aria-labelledby="landing-hero-heading">
          <div className="relative z-10 flex flex-col items-center pt-16 text-center sm:pt-24">
            <h1
              id="landing-hero-heading"
              className="font-serif text-4xl font-bold tracking-tight text-ink sm:text-5xl md:text-6xl"
            >
              {t("common.appName")}
            </h1>
            <p className="mt-4 max-w-2xl text-balance text-base leading-relaxed text-ink-muted sm:text-lg">
              {t("footer.tagline")}
            </p>
            <ul className="mt-6 flex flex-wrap items-center justify-center gap-2">
              <li>
                <Badge variant="outline">{t("landing.trust.openSource")}</Badge>
              </li>
              <li>
                <Badge variant="outline">{t("landing.trust.bilingual")}</Badge>
              </li>
              <li>
                <Badge variant="outline">
                  {t("landing.trust.certificates")}
                </Badge>
              </li>
            </ul>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Link to="/courses">
                <Button size="lg">
                  {t("dashboard.browseAllCta")}
                  <ArrowRight
                    className="ml-1.5 h-4 w-4"
                    strokeWidth={1.75}
                    aria-hidden
                  />
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
          </div>
        </section>

        {/* ── Value rows ──────────────────────────────────────────── */}
        <section
          aria-labelledby="landing-value-heading"
          className="mt-20 sm:mt-28"
        >
          <div className="mx-auto max-w-2xl text-center">
            <h2
              id="landing-value-heading"
              className="font-serif text-2xl font-semibold tracking-tight sm:text-3xl"
            >
              {t("landing.value.heading")}
            </h2>
            <p className="mt-2 text-sm text-ink-muted">
              {t("landing.value.subheading")}
            </p>
          </div>

          <div className="mt-12 flex flex-col gap-16 sm:mt-16 sm:gap-20">
            <ValueRow
              eyebrow={t("landing.value.structure.eyebrow")}
              title={t("landing.value.structure.title")}
              body={t("landing.value.structure.body")}
              visual={<StructureMock />}
            />
            <ValueRow
              eyebrow={t("landing.value.assessment.eyebrow")}
              title={t("landing.value.assessment.title")}
              body={t("landing.value.assessment.body")}
              visual={<AssessmentMock />}
              reverse
            />
            <ValueRow
              eyebrow={t("landing.value.certificates.eyebrow")}
              title={t("landing.value.certificates.title")}
              body={t("landing.value.certificates.body")}
              visual={<CertificateMock />}
            />
            <ValueRow
              eyebrow={t("landing.value.bilingual.eyebrow")}
              title={t("landing.value.bilingual.title")}
              body={t("landing.value.bilingual.body")}
              visual={<MultilingualMock />}
              reverse
            />
          </div>
        </section>

        {/* ── How it works ────────────────────────────────────────── */}
        <section
          aria-labelledby="landing-how-heading"
          className="mt-20 rounded-lg bg-muted/40 px-6 py-10 sm:mt-28 sm:px-10 sm:py-12"
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

        {/* ── Final CTA ───────────────────────────────────────────── */}
        <section className="mt-20 flex flex-col items-center text-center sm:mt-28">
          <h2 className="font-serif text-2xl font-semibold tracking-tight sm:text-3xl">
            {t("landing.finalCta.heading")}
          </h2>
          <p className="mt-3 max-w-xl text-balance text-sm text-ink-muted sm:text-base">
            {t("landing.finalCta.body")}
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            <Link to="/register">
              <Button size="lg">
                {t("landing.finalCta.primary")}
                <ArrowRight
                  className="ml-1.5 h-4 w-4"
                  strokeWidth={1.75}
                  aria-hidden
                />
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
      <Footer />
    </div>
  );
}

interface ValueRowProps {
  eyebrow: string;
  title: string;
  body: string;
  visual: React.ReactNode;
  /** Puts the visual on the left / text on the right at ``lg+``, so
   *  consecutive rows alternate sides instead of reading as a repeated
   *  template block. */
  reverse?: boolean;
}

function ValueRow({ eyebrow, title, body, visual, reverse }: ValueRowProps) {
  return (
    <div className="grid grid-cols-1 items-center gap-6 lg:grid-cols-2 lg:gap-12">
      <div className={reverse ? "lg:order-2" : undefined}>
        <Eyebrow>{eyebrow}</Eyebrow>
        <h3 className="mt-2 font-serif text-xl font-semibold tracking-tight text-ink sm:text-2xl">
          {title}
        </h3>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-ink-muted sm:text-base">
          {body}
        </p>
      </div>
      <div className={reverse ? "lg:order-1" : undefined}>{visual}</div>
    </div>
  );
}

interface StepProps {
  n: number;
  text: string;
}

function Step({ n, text }: StepProps) {
  return (
    <li className="flex items-start gap-3">
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-semibold text-brand-foreground">
        {n}
      </span>
      <p className="pt-0.5 text-sm leading-relaxed text-ink">{text}</p>
    </li>
  );
}

/** Mini module/chapter checklist — illustrates course structure. */
function StructureMock() {
  const { t } = useTranslation();
  return (
    <div className="surface-card mx-auto max-w-sm rounded-lg p-5">
      <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-ink-muted">
        <BookOpen className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        {t("landing.value.structure.module")}
      </p>
      <ul className="mt-4 space-y-2.5">
        <li className="flex items-center gap-2.5 text-sm text-ink">
          <Check
            className="h-4 w-4 shrink-0 text-success"
            strokeWidth={1.75}
            aria-hidden
          />
          {t("landing.value.structure.chapter1")}
        </li>
        <li className="flex items-center gap-2.5 text-sm text-ink">
          <Check
            className="h-4 w-4 shrink-0 text-success"
            strokeWidth={1.75}
            aria-hidden
          />
          {t("landing.value.structure.chapter2")}
        </li>
        <li className="flex items-center gap-2.5 text-sm text-ink-muted">
          <Circle className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden />
          {t("landing.value.structure.chapter3")}
        </li>
      </ul>
    </div>
  );
}

/** Mini quiz question card — illustrates teacher-graded assessment. */
function AssessmentMock() {
  const { t } = useTranslation();
  return (
    <div className="surface-card mx-auto max-w-sm rounded-lg p-5">
      <Badge variant="infoSubtle">
        <PenLine className="mr-1 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        {t("landing.value.assessment.gradedBadge")}
      </Badge>
      <p className="mt-3 text-sm font-medium leading-relaxed text-ink">
        {t("landing.value.assessment.sampleQuestion")}
      </p>
    </div>
  );
}

/** Mini certificate card — illustrates number-verifiable certificates. */
function CertificateMock() {
  const { t } = useTranslation();
  return (
    <div className="surface-card mx-auto max-w-sm rounded-lg p-6 text-center">
      <span className="mx-auto inline-flex h-10 w-10 items-center justify-center rounded-full bg-brand/10 text-brand-ink">
        <Award className="h-5 w-5" strokeWidth={1.75} aria-hidden />
      </span>
      <p className="mt-3 font-serif text-base font-semibold text-ink">
        {t("landing.value.certificates.certTitle")}
      </p>
      <div className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-edge px-2.5 py-1 text-xs text-ink-muted">
        <ShieldCheck className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
        {t("landing.value.certificates.verifyLabel")}
      </div>
    </div>
  );
}

/**
 * Mini locale fan-out — illustrates the auto-translation pipeline.
 *
 * It was called ``BilingualMock`` and it drew two badges, RU and EN, which
 * is what the product was when it was written. It sat a few centimetres
 * under a trust badge reading "Four languages: RU · EN · DE · UK" and body
 * copy promising English, German and Ukrainian — so the picture contradicted
 * the sentence above it, on the page whose whole job is to be believed.
 *
 * Derived from ``SUPPORTED_LOCALES`` rather than listed, so the picture
 * cannot fall behind the product a second time: the source language on the
 * left, everything it fans out into on the right.
 */
function MultilingualMock() {
  const { t } = useTranslation();
  const targets = SUPPORTED_LOCALES.filter((code) => code !== DEFAULT_LOCALE);
  return (
    <div className="surface-card mx-auto max-w-sm rounded-lg p-5 text-center">
      <div className="flex flex-wrap items-center justify-center gap-2">
        {/* The language courses are authored in — the input to the pipeline. */}
        <span className="rounded-md bg-brand/10 px-3 py-1.5 text-sm font-medium text-brand-ink">
          {DEFAULT_LOCALE.toUpperCase()}
        </span>
        <Languages
          className="h-4 w-4 shrink-0 text-ink-muted"
          strokeWidth={1.75}
          aria-hidden
        />
        {targets.map((code) => (
          <span
            key={code}
            className="rounded-md bg-muted px-3 py-1.5 text-sm font-medium text-ink-muted"
          >
            {code.toUpperCase()}
          </span>
        ))}
      </div>
      <p className="mt-3 text-xs text-ink-muted">
        {t("landing.value.bilingual.caption")}
      </p>
    </div>
  );
}
