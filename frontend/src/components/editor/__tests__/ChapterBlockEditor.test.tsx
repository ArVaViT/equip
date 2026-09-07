import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import type { ChapterBlock } from "@/types"
import ChapterBlockEditor from "../ChapterBlockEditor"

vi.mock("@/components/editor/RichTextEditor", () => ({
  default: ({ content, onChange }: { content: string; onChange: (html: string) => void }) => (
    <textarea aria-label="content" value={content} onChange={(e) => onChange(e.target.value)} />
  ),
}))

const textBlock: ChapterBlock = {
  id: "b-1",
  chapter_id: "ch-1",
  block_type: "text",
  order_index: 0,
  content: "<p>Деяния 1</p>",
  quiz_id: null,
  assignment_id: null,
  file_bucket: null,
  file_path: null,
  file_name: null,
}

// Plain functions rather than `vi.fn()` — see TextBlockEditor.test.tsx for why
// a rejected promise must not pass through a spy.
let updateImpl: (id: string, data: { content?: string | null }) => Promise<ChapterBlock> = async (
  id,
  data,
) => ({ ...textBlock, id, content: data.content ?? null })
vi.mock("@/services/courses", () => ({
  coursesService: {
    getChapterBlocksForEdit: async () => [textBlock],
    updateBlock: (id: string, data: { content?: string | null }) => updateImpl(id, data),
  },
}))
vi.mock("@/services/api", () => ({ default: { put: () => Promise.resolve({ data: {} }) } }))
// FileBlockEditor → services/storage → the Supabase client, which refuses to
// construct without env. None of that runs here; the module just has to load.
vi.mock("@/lib/supabase", () => ({ supabase: {} }))
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: { id: "t-1" } }) }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))
vi.mock("@/components/ui/alert-dialog", () => ({ useConfirm: () => async () => true }))

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function fireBeforeUnload(): boolean {
  const event = new Event("beforeunload", { cancelable: true })
  window.dispatchEvent(event)
  return event.defaultPrevented
}

async function elapse(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

async function renderAndExpand() {
  render(<ChapterBlockEditor courseId="c-1" chapterId="ch-1" />, { wrapper: Wrapper })
  await elapse(0)
  fireEvent.click(screen.getByText("Text"))
  return screen.getByLabelText("content")
}

describe("ChapterBlockEditor — leaving the page with an unsaved block", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    window.localStorage.clear()
    updateImpl = async (id, data) => ({ ...textBlock, id, content: data.content ?? null })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("asks before the page is left while a block's text has not reached the server", async () => {
    const field = await renderAndExpand()
    expect(fireBeforeUnload()).toBe(false)

    fireEvent.change(field, { target: { value: "<p>Вставлено, ещё не сохранено</p>" } })
    expect(fireBeforeUnload()).toBe(true)

    await elapse(2000)
    expect(fireBeforeUnload()).toBe(false)
  })

  it("keeps asking while the send after collapsing the block is still in flight", async () => {
    let release: (b: ChapterBlock) => void = () => {}
    updateImpl = (id, data) =>
      new Promise((resolve) => {
        release = resolve
        void id
        void data
      })
    const field = await renderAndExpand()
    fireEvent.change(field, { target: { value: "<p>Вставлено</p>" } })

    // Collapse: the editor is gone, the request is not back yet.
    fireEvent.click(screen.getByText("Text"))
    await elapse(0)
    expect(screen.queryByLabelText("content")).toBeNull()
    expect(fireBeforeUnload()).toBe(true)

    await act(async () => {
      release({ ...textBlock, content: "<p>Вставлено</p>" })
    })
    expect(fireBeforeUnload()).toBe(false)
  })

  it("keeps asking when that send failed, because only this browser has the text", async () => {
    updateImpl = () => Promise.reject(new Error("offline"))
    const field = await renderAndExpand()
    fireEvent.change(field, { target: { value: "<p>Вставлено</p>" } })
    fireEvent.click(screen.getByText("Text"))
    await elapse(0)

    expect(fireBeforeUnload()).toBe(true)
  })
})
