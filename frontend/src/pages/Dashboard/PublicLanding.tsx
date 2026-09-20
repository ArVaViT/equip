import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useReducedMotion } from "motion/react";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import Footer from "@/components/layout/Footer";
import { Section } from "@/components/layout/Section";
import { HeroVideo } from "./landing/HeroVideo";
import { ScrollReveal } from "./landing/ScrollReveal";

/**
 * Marketing landing rendered at ``/`` for unauthenticated visitors.
 *
 * REBUILT 2026-09-20, from nothing, on Vadym's instruction. What it replaced
 * and why it had to go:
 *
 * The previous page was four alternating text rows, each with a small drawn
 * mock beside it, then a three-step list, then a closing card. Everything was
 * the same weight, so nothing led; the only motion on it was one entrance
 * animation repeated four times; and a reader who wanted to know what this
 * platform is had to work through a great deal of prose to find out. Vadym's
 * words, and they were fair: «какие-то чанки информации, все плотно».
 *
 * An intermediate attempt added production screenshots to those same rows.
 * That made it worse, and the reason is worth keeping: it *added*. The brief
 * was less, and it was answered with more.
 *
 * So the shape now is three screens and nothing else:
 *
 * 1. **The claim, over a moving scene.** One sentence, one action, and a
 *    WebGL group of leaves that squares up as the page scrolls and tilts
 *    toward the cursor — the slogan as an object rather than a second
 *    paragraph.
 * 2. **The video.** A minute explaining what this is and what problem it
 *    solves, which is Vadym's to produce. Until that file exists the section
 *    renders nothing: a placeholder frame advertising a video that is not
 *    there is worse than no section at all.
 * 3. **Three claims and the way in.** A few words each. Anything needing a
 *    paragraph belongs in the video, not here.
 *
 * SEO. The h1 still spends itself on the claim rather than the brand, and
 * /courses, /register and /login are all still reachable as real anchors —
 * `__tests__/PublicLanding.test.tsx` pins exactly that, because the crawler
 * contract has to survive a redesign.
 */

// `three` is ~150KB gzipped, larger than the whole app shell. It is reached
// only from here, only after this module renders, and never by a student
// opening a lesson.
const HeroScene = lazy(() => import("./landing/HeroScene"));

export function PublicLanding() {
  const { t } = useTranslation();
  const prefersReducedMotion = useReducedMotion();

  return (
    <div className="w-full">
      {/* ── 1. The claim ─────────────────────────────────────────── */}
      {/* `isolate` gives the section its own stacking context, so the canvas
          can sit at z-0 behind the words without falling behind the page
          background. A negative z-index did exactly that: the scene rendered
          every frame and was invisible the whole time. */}
      <section
        className="relative isolate flex min-h-[88svh] items-center justify-center overflow-hidden"
        aria-labelledby="landing-hero-heading"
      >
        {/* Decoration in the strict sense: the section reads identically
            with it absent, which is what happens under reduced motion,
            without WebGL, and for the first moments of every load. */}
        {!prefersReducedMotion && (
          <Suspense fallback={null}>
            <HeroScene className="pointer-events-none absolute inset-0 z-0" />
          </Suspense>
        )}

        <div className="container relative z-10 mx-auto flex max-w-3xl flex-col items-center px-4 text-center">
          <h1
            id="landing-hero-heading"
            className="text-balance font-serif text-4xl font-bold leading-[1.05] tracking-tight text-ink sm:text-6xl md:text-7xl"
          >
            {t("landing.hero.manifesto")}
          </h1>
          <p className="mt-6 max-w-xl text-balance text-base leading-relaxed text-ink-muted sm:text-lg">
            {t("landing.hero.subline")}
          </p>

          {/* One action. The old hero offered five — two buttons, a text
              link and both header links — which is a page that has not
              decided what it wants from a visitor. */}
          <div className="mt-10">
            <Link to="/courses">
              <Button size="lg">
                {t("dashboard.browseAllCta")}
                <ArrowRight className="ml-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </Link>
          </div>

          <p className="mt-8 text-xs uppercase tracking-[0.14em] text-ink-muted">
            {t("landing.hero.facts")}
          </p>
          <p className="mt-6 text-sm text-ink-muted">
            <Link to="/register" className="font-medium text-brand hover:text-brand-ink">
              {t("landing.hero.registerCta")}
            </Link>
            <span className="px-2 text-line" aria-hidden>
              ·
            </span>
            <Link to="/login" className="font-medium text-brand hover:text-brand-ink">
              {t("common.signIn")}
            </Link>
          </p>
        </div>
      </section>

      {/* ── 2. The minute that explains it ───────────────────────── */}
      <HeroVideo />

      {/* ── 3. Three claims, then the way in ─────────────────────── */}
      {/* `<Section>` rather than another bespoke `container mx-auto …`
          string: the geometry census in `Section.test.tsx` caps how many
          distinct page shells may exist, and a landing page is not special
          enough to be the nineteenth. */}
      <Section as="section" aria-label={t("landing.value.heading")} className="py-24 sm:py-32">
        <div className="flex flex-col gap-20 sm:gap-28">
          {/* Literal keys, one call per string — a template key would be
              invisible to the ``keyCoverage`` check (docs/I18N.md). */}
          <ScrollReveal>
            <Claim
              title={t("landing.value.structure.title")}
              body={t("landing.value.structure.body")}
            />
          </ScrollReveal>
          <ScrollReveal>
            <Claim
              title={t("landing.value.assessment.title")}
              body={t("landing.value.assessment.body")}
            />
          </ScrollReveal>
          <ScrollReveal>
            <Claim
              title={t("landing.value.certificates.title")}
              body={t("landing.value.certificates.body")}
            />
          </ScrollReveal>
        </div>

        <ScrollReveal className="mt-28 flex flex-col items-center text-center sm:mt-36">
          <h2 className="font-serif text-2xl font-semibold tracking-tight text-ink sm:text-4xl">
            {t("landing.finalCta.heading")}
          </h2>
          <p className="mt-3 text-ink-muted">{t("landing.finalCta.body")}</p>
          <div className="mt-8">
            <Link to="/register">
              <Button size="lg">
                {t("landing.finalCta.primary")}
                <ArrowRight className="ml-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </Link>
          </div>
        </ScrollReveal>
      </Section>

      <Footer />
    </div>
  );
}

/** One claim: a few words and a line. Anything longer belongs in the video. */
function Claim({ title, body }: { title: string; body: string }) {
  return (
    <div className="max-w-2xl">
      <h3 className="font-serif text-2xl font-semibold leading-tight tracking-tight text-ink sm:text-4xl">
        {title}
      </h3>
      <p className="mt-4 text-base leading-relaxed text-ink-muted sm:text-lg">{body}</p>
    </div>
  );
}

export default PublicLanding;
