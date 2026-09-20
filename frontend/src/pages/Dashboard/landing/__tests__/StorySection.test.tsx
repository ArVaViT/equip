import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { afterEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { StorySection } from "@/pages/Dashboard/landing/StorySection"

/**
 * The claims render in two shapes, and only one of them has a scroll track.
 *
 * Wide screens get a sticky track whose progress drives which caption is on
 * screen. Phones get a plain column: there is no backdrop behind them, so a
 * three-screen track would be three empty screens with one sentence each.
 *
 * The rule this file protects is about the seam between those two shapes.
 * `useScroll({ target })` must be mounted *together with* the element it
 * points at. When the hook lived in the outer component it ran in both
 * shapes, and in the plain-column shape its ref was never attached — motion
 * then threw `Target ref is defined but not hydrated` from a microtask
 * after the effects had flushed.
 *
 * That invariant compiles away in a production build, so the live site was
 * unaffected and nothing in the browser said a word. In development and in
 * CI it is an uncaught exception: on 2026-09-20 it turned the frontend
 * suite red with 191 files and 1,471 tests all passing and no test failing,
 * which is a failure mode worth a test of its own.
 */

const spy = vi.hoisted(() => ({ useScroll: vi.fn() }))

vi.mock("motion/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("motion/react")>()
  return {
    ...actual,
    useScroll: (options?: Parameters<typeof actual.useScroll>[0]) => {
      spy.useScroll(options)
      return actual.useScroll(options)
    },
  }
})

/** jsdom has no `matchMedia`; give it one that answers by query. */
function stubMatchMedia(wide: boolean) {
  const original = window.matchMedia
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      // The only two queries the landing page asks about.
      matches: query.includes("min-width") ? wide : false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  })
  return () => {
    if (original) window.matchMedia = original
    else Reflect.deleteProperty(window, "matchMedia")
  }
}

function renderStory() {
  return render(
    <I18nextProvider i18n={i18n}>
      <StorySection />
    </I18nextProvider>,
  )
}

let restore: (() => void) | undefined

afterEach(() => {
  restore?.()
  restore = undefined
  spy.useScroll.mockClear()
})

describe("StorySection", () => {
  it("tracks no scroll target on a narrow screen, where it renders no track", async () => {
    restore = stubMatchMedia(false)
    renderStory()
    // motion defers its attempt to a microtask on its own frame loop, so
    // let the queue drain before concluding anything.
    await Promise.resolve()
    expect(spy.useScroll).not.toHaveBeenCalled()
  })

  it("tracks no scroll target when the environment has no matchMedia at all", async () => {
    // Old mobile engines and jsdom itself. The component falls back to the
    // column, and the hook must fall back with it.
    renderStory()
    await Promise.resolve()
    expect(spy.useScroll).not.toHaveBeenCalled()
  })

  it("still says all three things in the column", () => {
    renderStory()
    for (const key of [
      "landing.value.structure.title",
      "landing.value.assessment.title",
      "landing.value.certificates.title",
    ]) {
      expect(screen.getByText(i18n.t(key))).toBeInTheDocument()
    }
  })

  it("tracks a target that is actually in the document on a wide screen", async () => {
    restore = stubMatchMedia(true)
    renderStory()
    await Promise.resolve()
    expect(spy.useScroll).toHaveBeenCalled()
    for (const [options] of spy.useScroll.mock.calls) {
      const target = (options as { target?: { current: HTMLElement | null } } | undefined)?.target
      // The point of the whole exercise: whenever the hook runs, its ref
      // has an element, and that element is in the document.
      expect(target?.current).toBeTruthy()
      expect(target?.current?.isConnected).toBe(true)
    }
  })
})
