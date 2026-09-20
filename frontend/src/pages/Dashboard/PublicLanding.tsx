import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useReducedMotion } from "motion/react";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import Footer from "@/components/layout/Footer";
import { HeroVideo } from "./landing/HeroVideo";
import { ScrollReveal } from "./landing/ScrollReveal";
import { StorySection } from "./landing/StorySection";
import { CourseShowcase } from "./landing/CourseShowcase";
import { ProductTour } from "./landing/ProductTour";

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
            <HeroScene
              // The canvas ends where the section does, and a plane crossing
              // that line was getting sliced flat — a hard horizontal edge
              // across the picture, which reads as a rendering bug rather
              // than as a composition. Fading the bottom of the canvas lets
              // the scene run out of the frame instead of being cut off.
              className="pointer-events-none absolute inset-0 z-0 [mask-image:linear-gradient(to_bottom,black_62%,transparent_100%)]"
            />
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

      {/* ── 2. Three claims, told over one moving scene ──────────── */}
      <StorySection />

      {/* ── 3. Twenty seconds of it working ──────────────────────── */}
      {/* Silent, looping, and not the film. The film is a minute with a
          voice and lives at the end, where Vadym wants it; this is the
          product in motion — a lesson changing language — and it earns its
          place here because the three claims above it have just been made
          and this is what they look like. */}
      <ProductTour />

      {/* ── 4. What is actually on the shelf ─────────────────────── */}
      {/* Everything above argues about how the platform teaches; this is
          the first thing that says what is on it. Live from the public
          catalogue endpoint, so it cannot advertise a course that was
          unpublished last month. */}
      <CourseShowcase />

      {/* ── 5. The way in ────────────────────────────────────────── */}
      {/* `<Section>` rather than another bespoke `container mx-auto …`
          string: the geometry census in `Section.test.tsx` caps how many
          distinct page shells may exist, and a landing page is not special
          enough to be the nineteenth. */}
      {/* A close, not another block.
          At `text-2xl` in a padded section this read as one more row among
          the rows — «часть „Готовы начать?" немного странная» — arriving
          after a pinned scene and a travelling shelf and asking for less
          attention than either. It gets a screen of its own now, and the
          question is set at the size of the opening claim, because it is
          the same sentence asked back. */}
      {/* `min-h-[70svh]` plus `py-24` on top of the shelf's own sticky
          screen left a long empty stretch before the question — «перед
          ready to start много места и нет мушина в том моменте». The
          padding is gone, the screen is what holds it, and `ScrollReveal`
          gives the block the same parallax the claims have, so the approach
          to the close is not the one moment on the page where everything
          stops. */}
      <section
        aria-label={t("landing.value.heading")}
        className="flex min-h-[70svh] items-center justify-center px-4"
      >
        <ScrollReveal className="flex flex-col items-center text-center">
          <h2 className="max-w-3xl text-balance font-serif text-4xl font-bold leading-[1.05] tracking-tight text-ink sm:text-6xl">
            {t("landing.finalCta.heading")}
          </h2>
          <p className="mt-6 max-w-md text-balance text-base text-ink-muted sm:text-lg">
            {t("landing.finalCta.body")}
          </p>
          <div className="mt-10">
            <Link to="/register">
              <Button size="lg">
                {t("landing.finalCta.primary")}
                <ArrowRight className="ml-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </Link>
          </div>
        </ScrollReveal>
      </section>

      {/* ── 6. The film ──────────────────────────────────────────── */}
      {/* Deliberately last. Vadym: «его надо явно ближе к концу, чтоб он не
          было первым впечатлением» — a minute of explanation is what you
          offer somebody already deciding, not what you open with. */}
      <HeroVideo />

      <Footer />
    </div>
  );
}

export default PublicLanding;
