import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import type { ChapterBlock } from "@/types"
import ChapterBlockEditor from "../ChapterBlockEditor"

vi.mock("@/components/editor/RichTextEditor", () => ({
  default: ({ content }: { content: string }) => <textarea aria-label="content" defaultValue={content} />,
}))

const block = (id: string, i: number, content: string): ChapterBlock => ({
  id,
  chapter_id: "ch-1",
  block_type: "text",
  order_index: i,
  content,
  quiz_id: null,
  assignment_id: null,
  file_bucket: null,
  file_path: null,
  file_name: null,
})

const reorders: Array<Array<{ id: string; order_index: number }>> = []
vi.mock("@/services/courses", () => ({
  coursesService: {
    getChapterBlocksForEdit: async () => [block("b-1", 0, "<p>Первая мысль урока</p>"), block("b-2", 1, "<p>Вторая</p>")],
    updateBlock: async (id: string) => ({ id }),
    reorderBlocks: async (_c: string, order: Array<{ id: string; order_index: number }>) => {
      reorders.push(order)
    },
  },
}))
vi.mock("@/services/api", () => ({ default: { put: () => Promise.resolve({ data: {} }) } }))
vi.mock("@/lib/supabase", () => ({ supabase: {} }))
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "t-1" } }) }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("ChapterBlockEditor — a lesson reads as a document", () => {
  it("opens every block, and a folded one shows its first words", async () => {
    render(<ChapterBlockEditor courseId="c-1" chapterId="ch-1" />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getAllByLabelText("content")).toHaveLength(2))

    fireEvent.click(screen.getAllByText("Text")[0]!)
    expect(screen.getAllByLabelText("content")).toHaveLength(1)
    expect(screen.getByText("Первая мысль урока")).toBeInTheDocument()
  })

  it("moves a block down with a button, for screens where dragging does not work", async () => {
    render(<ChapterBlockEditor courseId="c-1" chapterId="ch-1" />, { wrapper: Wrapper })
    await waitFor(() => expect(screen.getAllByLabelText("content")).toHaveLength(2))
    const [first] = screen.getAllByRole("button", { name: /down/i })
    fireEvent.click(first!)
    await waitFor(() => expect(reorders[reorders.length - 1]).toEqual([
      { id: "b-2", order_index: 0 },
      { id: "b-1", order_index: 1 },
    ]))
    // The top block cannot move up, the bottom one cannot move down.
    const up = screen.getAllByRole("button", { name: /up/i })
    expect(up[0]).toBeDisabled()
  })
})
