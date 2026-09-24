import { lazy, Suspense, useEffect, useState } from "react";
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

// `three` is ~126KB gzipped, larger than the whole app shell. It is reached
// only from here, only after this module renders, and never by a student
// opening a lesson.
const LandingBackdrop = lazy(() => import("./landing/LandingBackdrop"));

export function PublicLanding() {
  const { t } = useTranslation();
  const prefersReducedMotion = useReducedMotion();

  // The backdrop is a desktop luxury, and on a phone it was three things at
  // once: unreadable, expensive and hot. At 390px the planes are the size of
  // the screen, so they stop reading as texture and start reading as grey
  // shapes lying across the headline; it costs 128KB of `three` on a mobile
  // connection; and it keeps a GPU busy on the device least able to afford
  // it. Below `lg` the page is simply clean — which is what a phone wants
  // from a landing page anyway.
  const [wideEnough, setWideEnough] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(min-width: 1024px)");
    const sync = () => setWideEnough(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);
  const showBackdrop = wideEnough && !prefersReducedMotion;

  // Weight and a pause at every scene — «как у них на сайте продумано, что
  // на каждом блоке человек задерживается». The how and the why, including
  // why it is not CSS scroll-snap, are in `landing/pageScroll.ts`. Same
  // fence as the backdrop: desktop, motion allowed, loaded lazily so the
  // library never reaches a phone or the app shell.
  useEffect(() => {
    if (!showBackdrop) return;
    let stop: (() => void) | null = null;
    let cancelled = false;
    void import("./landing/pageScroll").then(({ default: start }) => {
      if (!cancelled) stop = start();
    });
    return () => {
      cancelled = true;
      stop?.();
    };
  }, [showBackdrop]);

  return (
    <div className="relative w-full">
      {/* One scene behind the entire page rather than one per section.
          Pinned canvases were released at the end of their own tracks, so
          the shelf, the close and the film sat against a still page —
          «почему он дальше не продолжается до конца страницы?». Fixed has
          no track to leave. */}
      {showBackdrop && (
        <Suspense fallback={null}>
          <LandingBackdrop className="pointer-events-none fixed inset-0 z-0" />
        </Suspense>
      )}

      <div className="relative z-10">
      {/* ── 1. The claim ─────────────────────────────────────────── */}
      {/* `isolate` gives the section its own stacking context, so the canvas
          can sit at z-0 behind the words without falling behind the page
          background. A negative z-index did exactly that: the scene rendered
          every frame and was invisible the whole time. */}
      <section
        // No forced height on a phone. Centring a compact block inside 78svh
        // left a third of the screen empty under the links — on a desktop
        // that space is where the scene lives, and on a phone there is no
        // scene, so it was just a hole. The content sets the height; the
        // screen holds it from `sm` up, where the backdrop returns.
        className="relative flex items-center justify-center py-24 sm:min-h-[88svh] sm:py-0"
        aria-labelledby="landing-hero-heading"
        data-scene-stop="top"
      >
        <div className="container relative z-10 mx-auto flex max-w-3xl flex-col items-center px-5 text-center lg:max-w-5xl">
          <h1
            id="landing-hero-heading"
            // `text-balance` evens the line lengths, which on a wide screen
            // squeezed a short sentence into three stacked lines with a
            // column of air either side — «слишком сконцентрировано на
            // центре». Balanced up to `lg`, where it helps a phone; plain
            // wrapping above it, where the measure is wide enough to break
            // the sentence where it wants to.
            className="text-balance font-serif text-[2.5rem] font-bold leading-[1.05] tracking-tight text-ink sm:text-6xl md:text-7xl lg:text-pretty"
          >
            {t("landing.hero.manifesto")}
          </h1>
          <p className="mt-5 max-w-xl text-balance text-[1.0625rem] leading-relaxed text-ink-muted sm:mt-6 sm:text-lg">
            {t("landing.hero.subline")}
          </p>

          {/* Two actions, and only two.
              The old hero offered five — two buttons, a text link and both
              header links — which is a page that has not decided what it
              wants from a visitor. Then it went to one button with a line of
              facts and a «Create account · Sign In» pair under it: still
              three rows of choices, just smaller. Now it is the shape
              claude.com uses («Try Claude» / «Download for Mac»): the thing
              to do, filled, and the way back in for somebody who already
              has an account, outlined beside it. Registering is in the
              header and at the close; it does not need a third spot here.

              The facts line («FREE · OPEN SOURCE · RU EN DE UK ·
              VERIFIABLE CERTIFICATE») went with it — «лишний кусок». Each
              of those is said again, in a sentence, further down the page. */}
          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Link to="/courses">
              <Button size="lg">
                {t("dashboard.browseAllCta")}
                <ArrowRight className="ml-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
              </Button>
            </Link>
            <Link to="/login">
              <Button size="lg" variant="outline" className="bg-surface/70 backdrop-blur-sm">
                {t("common.signIn")}
              </Button>
            </Link>
          </div>
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
      {/* A full screen from `lg`, like every scene: resting on the close
          shows the close, not the bottom of the shelf and the top of the
          film around it. */}
      <section
        aria-label={t("landing.value.heading")}
        className="flex items-center justify-center px-5 py-20 sm:min-h-[52svh] sm:py-0 lg:min-h-[100svh]"
        data-scene-stop="center"
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

        {/* The last rest stop is the bottom of the page, so the wall that
            holds the film does not stop a reader short of the legal links. */}
        <div data-scene-stop="end">
          <Footer />
        </div>
      </div>
    </div>
  );
}

export default PublicLanding;
