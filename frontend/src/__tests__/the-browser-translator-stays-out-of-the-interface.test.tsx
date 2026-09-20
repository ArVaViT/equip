/**
 * The browser's translator may rewrite the lesson, not the interface.
 *
 * Chrome's translator replaces text nodes in place. React holds fibers
 * pointing at those nodes, and when it next reconciles them it asks the
 * DOM to insert a node next to a sibling that the translator has already
 * swapped out. The DOM refuses:
 *
 *   NotFoundError: Failed to execute 'insertBefore' on 'Node'
 *
 * Three readers met that between 2026-08-25 and 2026-09-19 — Chile,
 * Singapore, the United States, on `/`, `/login` and `/register`, always
 * with a button and an icon in the stack. Every one of them lost the page
 * to an ErrorBoundary.
 *
 * The rule this file pins has two halves, and each is useless alone:
 *
 * 1. The interface is not the browser's to translate. Equip ships four
 *    languages itself, so a second translator on top of i18next buys
 *    nothing and costs the crash above.
 * 2. The lesson body still is. A reader whose language Equip does not
 *    ship — Spanish, for the reader in Chile — has no other way to read
 *    it, and turning the translator off everywhere would have taken the
 *    text from them rather than protected it. It is safe there because
 *    that subtree comes from `dangerouslySetInnerHTML`: React keeps no
 *    child fibers inside it, so there is nothing to reconcile against.
 *
 * Losing half two is the failure this file is most likely to catch: the
 * cheap "fix" for the crash is a blanket notranslate, and it would pass
 * any test that only checked the first half.
 */

import { readFileSync } from "node:fs"
import { resolve } from "node:path"

import { describe, expect, it } from "vitest"

function indexHtml(): Document {
  // Parsed rather than pattern-matched. index.html explains this choice
  // in a comment that names the very tag it rejects, and a regex over the
  // raw text would read that prose as markup — stripping comments first
  // to dodge it is both fragile and indistinguishable from sanitisation,
  // which is what CodeQL rightly flagged. A parser has no such problem:
  // comments are not elements.
  const source = readFileSync(resolve(__dirname, "../../index.html"), "utf8")
  return new DOMParser().parseFromString(source, "text/html")
}

function chapterViewSource(): string {
  return readFileSync(resolve(__dirname, "../pages/Course/ChapterView.tsx"), "utf8")
}

describe("the browser translator stays out of the interface", () => {
  it("the document opts out of automatic translation", () => {
    expect(indexHtml().documentElement.getAttribute("translate")).toBe("no")
  })

  it("does so with the attribute, which a subtree can override", () => {
    // `<meta name="google" content="notranslate">` cannot be overridden
    // further down, so it would close the lesson body along with the
    // chrome. If it ever appears, half two of the rule above is gone.
    expect(indexHtml().querySelector('meta[name="google"][content="notranslate"]')).toBeNull()
  })

  it("the chapter body opts back in", () => {
    expect(chapterViewSource()).toMatch(/translate="yes"/)
  })

  it("the chapter body opts back in on the element React does not reconcile", () => {
    const source = chapterViewSource()
    const optIn = source.indexOf('translate="yes"')
    const injected = source.indexOf("dangerouslySetInnerHTML", optIn)
    const elementEnd = source.indexOf("/>", optIn)

    // Both on the same element: the opt-in is only safe where React holds
    // no child fibers.
    expect(optIn).toBeGreaterThan(-1)
    expect(injected).toBeGreaterThan(-1)
    expect(injected).toBeLessThan(elementEnd)
  })
})
