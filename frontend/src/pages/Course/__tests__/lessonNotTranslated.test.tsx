/**
 * A lesson with nothing in your language must say so.
 *
 * An empty text block renders as `null` — correctly, since an empty
 * paragraph is not content. But when *every* block is empty, which is
 * what a lesson nobody has translated looks like, the page came out
 * blank under its heading: indistinguishable from a browser that failed
 * to load something.
 *
 * "Nothing here" and "nothing here yet, in your language" are different
 * sentences, and the reader is owed the second one.
 */

import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { I18nextProvider } from "react-i18next"

import i18n from "@/i18n/config"
import { ChapterBodyBlocks } from "../ChapterView"
import type { ChapterBlock } from "@/types"

const block = (over: Partial<ChapterBlock>): ChapterBlock =>
  ({
    id: crypto.randomUUID(),
    chapter_id: "ch-1",
    block_type: "text",
    order_index: 0,
    content: "",
    ...over,
  }) as ChapterBlock

function renderBody(blocks: ChapterBlock[]) {
  return render(
    <I18nextProvider i18n={i18n}>
      <ChapterBodyBlocks blocks={blocks} loading={false} loadError={false} onRetry={() => {}} />
    </I18nextProvider>,
  )
}

describe("a lesson with nothing to read in this language", () => {
  it("says it is not translated yet rather than showing a blank page", () => {
    renderBody([block({ content: "" }), block({ content: "   " })])
    expect(screen.getByText(/not available in your language yet/i)).toBeInTheDocument()
  })

  it("renders the lesson when there is something to read", () => {
    renderBody([block({ content: "<p>Peter stood up among the brothers.</p>" })])
    expect(screen.getByText(/Peter stood up/)).toBeInTheDocument()
  })

  it("a non-text block is content in any language", () => {
    // A quiz or a file block carries no prose to translate; a lesson
    // that is one of those is not untranslated.
    renderBody([block({ block_type: "quiz", content: "" })])
    expect(screen.queryByText(/not available in your language yet/i)).not.toBeInTheDocument()
  })
})
