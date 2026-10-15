import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import type { ChapterBlock } from "@/types"

vi.mock("@/services/courses", () => ({ coursesService: {} }))
vi.mock("@/services/progress", () => ({ progressService: {} }))
vi.mock("@/services/storage", () => ({ storageService: {} }))

const { ChapterBodyBlocks } = await import("../ChapterView")

/**
 * In the preview the server sends a test, an assignment or a file without
 * its ids and path. The placeholder used to list all three kinds — «тест,
 * задание или файл» — for every one of them; the block knows which it is.
 */
const block = (over: Partial<ChapterBlock>): ChapterBlock =>
  ({
    chapter_id: "ch1",
    order_index: 0,
    content: null,
    quiz_id: null,
    assignment_id: null,
    file_bucket: null,
    file_path: null,
    file_name: null,
    ...over,
  }) as ChapterBlock

describe("a block withheld from the preview", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })

  it("says which kind of thing enrolling would open here", () => {
    render(
      <I18nextProvider i18n={i18n}>
        <ChapterBodyBlocks
          loading={false}
          loadError={false}
          onRetry={() => {}}
          blocks={[
            block({ id: "b1", block_type: "text", content: "<p>Читайте.</p>", order_index: 0 }),
            block({ id: "b2", block_type: "quiz", order_index: 1 }),
            block({ id: "b3", block_type: "assignment", order_index: 2 }),
            block({ id: "b4", block_type: "file", order_index: 3 }),
          ]}
        />
      </I18nextProvider>,
    )
    expect(screen.getByText("Читайте.")).toBeInTheDocument()
    expect(screen.getByText("Здесь тест — он откроется после записи")).toBeInTheDocument()
    expect(screen.getByText("Здесь задание — оно откроется после записи")).toBeInTheDocument()
    expect(screen.getByText("Здесь файл — он откроется после записи")).toBeInTheDocument()
    expect(screen.queryByText(/тест, задание или файл/i)).not.toBeInTheDocument()
  })
})
