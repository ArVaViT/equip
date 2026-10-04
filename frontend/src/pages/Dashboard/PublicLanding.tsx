import { lazy, Suspense, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useReducedMotion } from "motion/react";
import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { HeroVideo } from "./landing/HeroVideo";
import { ScrollReveal } from "./landing/ScrollReveal";
import { StorySection } from "./landing/StorySection";
import { CourseShowcase } from "./landing/CourseShowcase";
import { OrganizationsBand } from "./landing/OrganizationsBand";
import { Faq } from "./landing/Faq";
import { RevealFooter } from "./landing/RevealFooter";
import { ProductTour } from "./landing/ProductTour";
import { TEXT_VEIL } from "./landing/textVeil";

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
 * The shape now (2026-09-27), one scene per screen, over one moving
 * backdrop (`LandingBackdrop`):
 *
 * 1. **The claim.** One sentence, the offer in one line, two actions — with
 *    the product already showing beneath it.
 * 2. **The tour.** Twenty silent seconds of the product working.
 * 3. **Three claims.** Order, real assessment, every student in their own
 *    language — a few words each; anything longer belongs in the film.
 * 4. **The shelf.** The live catalogue.
 * 5. **The film.** A minute on what this is, for somebody already deciding.
 * 6. **Questions.** Five, closed by default, each a fact of the product.
 * 7. **The close.** The same sentence asked back, and the one action. The
 *    page ends on it; the footer comes up over it on one more push.
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

  // The backdrop runs on every width now.
  //
  // It was desktop-only until 2026-09-23, for three reasons that were each
  // true of the desktop scene shrunk onto a phone: the planes were the size
  // of the screen and read as grey shapes across the headline; `three` is
  // 128KB on a mobile connection; and the loop kept a GPU busy for nothing.
  // What that bought was a phone page of plain text — «адаптив слабый, на
  // телефоне должен быть вау-эффект». So the scene learned the phone instead
  // of leaving it: leaves sized to a portrait screen and lighter behind
  // text, a pixel-ratio cap, and a loop that stops drawing when nothing is
  // moving (see `LandingBackdrop`). The 128KB is still lazy — the hero text
  // and the button render before it arrives.
  //
  // `matchMedia` doubles as the "is this a real browser" check: jsdom lacks
  // it, and has no WebGL to give the scene either.
  const [canAnimate, setCanAnimate] = useState(false);
  const [wideEnough, setWideEnough] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    setCanAnimate(true);
    const query = window.matchMedia("(min-width: 1024px)");
    const sync = () => setWideEnough(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);
  const showBackdrop = canAnimate && !prefersReducedMotion;
  // Lenis and the wheel rules are about a wheel; a phone keeps its own
  // physics, so they stay desktop-only.
  const smoothScroll = wideEnough && !prefersReducedMotion;

  // Weight and a pause at every scene — «как у них на сайте продумано, что
  // на каждом блоке человек задерживается». The how and the why, including
  // why it is not CSS scroll-snap, are in `landing/pageScroll.ts`. Same
  // fence as the backdrop: desktop, motion allowed, loaded lazily so the
  // library never reaches a phone or the app shell.
  useEffect(() => {
    if (!smoothScroll) return;
    let stop: (() => void) | null = null;
    let cancelled = false;
    void import("./landing/pageScroll").then(({ default: start }) => {
      if (!cancelled) stop = start();
    });
    return () => {
      cancelled = true;
      stop?.();
    };
  }, [smoothScroll]);

  return (
    // `overflow-x-clip`, not `hidden`: the text veils reach 128px past their
    // blocks and pushed a phone's document to 518px in a 390px screen
    // (caught by e2e/no-sideways-scroll). `hidden` would make this div a
    // scroll container and break every `sticky` inside it; `clip` does not.
    //
    // Both axes since 2026-09-27. The footer is veiled too, and its veil
    // reached 144px past the bottom of the page — with only `x` clipped,
    // that was 144px of empty scrolling after the legal links, on every
    // width: «после футера много пустого места».
    <div className="relative w-full overflow-clip">
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
        //
        // Short of a full screen on every width since 2026-09-27, so the tour
        // shows under it on the first screen: Linear, Stripe, Brilliant,
        // Raycast, Dwell — every product page worth copying has the product
        // in view before the first scroll, and this one showed it on the
        // fifth screen.
        //
        // The room left is a fixed height, not a share of the screen, so the
        // same amount of tour shows on a short laptop as on a tall monitor:
        // 15rem on a phone — past a quarter of the portrait frame, which is
        // where the tour starts playing, so the first screen has the product
        // moving in it rather than the blank top edge of a still — and 11rem
        // from `sm`, where the frame's top carries its caption.
        className="relative flex min-h-[calc(100svh-2.75rem-15rem)] items-center justify-center py-12 sm:min-h-[calc(100svh-3rem-11rem)] sm:py-10"
        aria-labelledby="landing-hero-heading"
        data-scene-stop="top"
      >
        <div className={`container z-10 mx-auto flex max-w-3xl flex-col items-center px-5 text-center lg:max-w-5xl ${TEXT_VEIL}`}>
          {/* Weight 500, not 700. Bold Literata at display size read as a
              book blog; claude.com sets its serif display at regular weight
              and that is most of why it reads as expensive. The typeface
              stays — it is the one that holds Cyrillic — and every serif
              heading on this page moved together (2026-09-23). The lighter
              weight is also narrower, which let «not» climb onto the first
              line — «in order, not / in fragments», the claim broken through
              its middle. `max-w-4xl` puts the break back after the comma. */}
          <h1
            id="landing-hero-heading"
            // `text-balance` evens the line lengths, which on a wide screen
            // squeezed a short sentence into three stacked lines with a
            // column of air either side — «слишком сконцентрировано на
            // центре». Balanced up to `lg`, where it helps a phone; plain
            // wrapping above it, where the measure is wide enough to break
            // the sentence where it wants to.
            className="text-balance font-serif text-[2.5rem] font-medium leading-[1.05] tracking-[-0.03em] text-ink sm:text-6xl md:text-7xl lg:max-w-4xl lg:text-pretty"
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

      {/* ── 2. Twenty seconds of it working ──────────────────────── */}
      {/* Silent, looping, and not the film. The film is a minute with a
          voice and lives near the end, where Vadym wants it; this is the
          product in motion — a lesson changing language.
          Straight under the hero since 2026-09-27, and showing under it on
          the first screen. It used to come after the three claims, which
          put four screens of words between a visitor and the first look at
          the thing the words are about. */}
      <ProductTour />

      {/* ── 3. Three claims, told over one moving scene ──────────── */}
      <StorySection />

      {/* ── 4. What is actually on the shelf ─────────────────────── */}
      {/* Everything above argues about how the platform teaches; this is
          the first thing that says what is on it. Live from the public
          catalogue endpoint, so it cannot advertise a course that was
          unpublished last month. */}
      <CourseShowcase />

      {/* ── 4½. Who teaches here — absent until there are two ─────── */}
      <OrganizationsBand />

      {/* ── 5. The film ──────────────────────────────────────────── */}
      {/* Near the end, not first. Vadym: «его надо явно ближе к концу, чтоб
          он не было первым впечатлением» — a minute of explanation is what
          you offer somebody already deciding, not what you open with. But
          not after the close either: every page worth copying ends on its
          one action, and this one used to end on a video. */}
      <HeroVideo />

      {/* ── 6. Questions ──────────────────────────────────────────── */}
      {/* The doubts of somebody deciding, answered before the button. */}
      <Faq />

      {/* ── 7. The way in ────────────────────────────────────────── */}
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
        // The last screen, on every width: the page ends here and the footer
        // comes up over it (`RevealFooter`), so the close fills what is below
        // the header and the question sits in the middle of the final view.
        className="relative isolate flex min-h-[calc(100svh-2.75rem)] items-center justify-center px-5 md:min-h-[calc(100svh-3rem)]"
        data-scene-stop="center"
        // The pieces collect into one deck behind the question.
        data-backdrop-pose="gather"
      >
        {/* The one place the page lets colour glow. Two soft lights — the
            sage of the covers and a warm gold — behind the question, the way
            Linear, GitHub and Framer light the moment they ask you to act.
            Behind the text veil, so they read as a halo round the words and
            never under them. Blurred CSS gradients, not WebGL: nothing to
            load, nothing to run. Dimmer in the dark theme, where the gold at
            full strength came through the veil under the line below the
            question (2.59:1, measured). */}
        <div
          aria-hidden
          // The section's own height, not a fixed 44rem: taller than the
          // close on a phone, the light reached up into the FAQ's last answer
          // (2.68:1 in the dark theme, measured).
          className="pointer-events-none absolute inset-y-6 left-1/2 -z-10 w-[min(60rem,170vw)] -translate-x-1/2 blur-2xl dark:opacity-55"
          style={{
            background:
              "radial-gradient(closest-side at 30% 62%, hsl(140 32% 48% / 0.55), transparent)," +
              "radial-gradient(closest-side at 72% 36%, hsl(38 72% 60% / 0.5), transparent)," +
              "radial-gradient(closest-side at 50% 50%, hsl(160 30% 55% / 0.25), transparent)",
          }}
        />
        <ScrollReveal className={`flex flex-col items-center text-center ${TEXT_VEIL}`}>
          <h2 className="max-w-3xl text-balance font-serif text-4xl font-medium leading-[1.05] tracking-[-0.03em] text-ink sm:text-6xl">
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

      </div>

      {/* The page ends on the close. One more push brings the footer up
          over its bottom edge instead of scrolling the question away — see
          `RevealFooter`. */}
      <RevealFooter />
    </div>
  );
}

export default PublicLanding;
