import { StrictMode, type ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { toast } from "@/lib/toast"
import type { ChapterBlock } from "@/types"
import { TextBlockEditor } from "../TextBlockEditor"

// ---------------------------------------------------------------------------
// Doubles
// ---------------------------------------------------------------------------

// The editor is TipTap, which does not run under jsdom. A textarea that calls
// the same `onChange(html)` is all the component needs from it.
vi.mock("@/components/editor/RichTextEditor", () => ({
  default: ({ content, onChange }: { content: string; onChange: (html: string) => void }) => (
    <textarea aria-label="content" value={content} onChange={(e) => onChange(e.target.value)} />
  ),
}))

// A plain function, not `vi.fn()`. A `vi.fn()` that returns a rejected promise
// records that promise in `mock.results`, and the runner reports it as an
// unhandled rejection before the component's `catch` has run — so the
// failure path cannot be exercised through a spy at all.
type UpdateArgs = [blockId: string, data: { content?: string | null }]
let updateCalls: UpdateArgs[] = []
let updateImpl: (...args: UpdateArgs) => Promise<ChapterBlock> = async (id, data) => ({
  ...baseBlock,
  id,
  content: data.content ?? null,
})
vi.mock("@/services/courses", () => ({
  coursesService: {
    updateBlock: (...args: UpdateArgs) => {
      updateCalls.push(args)
      return updateImpl(...args)
    },
  },
}))

let keepalivePuts: unknown[][] = []
vi.mock("@/services/api", () => ({
  default: {
    put: (...args: unknown[]) => {
      keepalivePuts.push(args)
      return Promise.resolve({ data: {} })
    },
  },
}))

vi.mock("@/context/useAuth", () => ({
  useAuth: () => ({ user: { id: "t-1", full_name: "Учитель" } }),
}))

vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const baseBlock: ChapterBlock = {
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

const DRAFT_KEY = "equip.draft.block.t-1.b-1"
const PASTED = "<p>Деяния 1</p><p>Вставлено из Word</p>"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function renderEditor(
  overrides: Partial<ChapterBlock> = {},
  props: { onUnsavedChange?: (unsaved: boolean) => void; strict?: boolean } = {},
) {
  const onSaved = vi.fn()
  const block = { ...baseBlock, ...overrides }
  const tree = (
    <TextBlockEditor block={block} onSaved={onSaved} onUnsavedChange={props.onUnsavedChange} />
  )
  const utils = render(props.strict ? <StrictMode>{tree}</StrictMode> : tree, { wrapper: Wrapper })
  return { ...utils, onSaved, block }
}

function typeInto(value: string) {
  fireEvent.change(screen.getByLabelText("content"), { target: { value } })
}

async function elapse(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state })
}

// ---------------------------------------------------------------------------

describe("TextBlockEditor — pasted text never disappears silently", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    updateCalls = []
    keepalivePuts = []
    updateImpl = async (id, data) => ({ ...baseBlock, id, content: data.content ?? null })
    vi.mocked(toast).mockClear()
    window.localStorage.clear()
  })

  afterEach(() => {
    Reflect.deleteProperty(document, "visibilityState")
    vi.useRealTimers()
  })

  describe("collapsing the block", () => {
    it("sends the text the debounce had not sent yet, instead of throwing it away", async () => {
      const { unmount, onSaved } = renderEditor()
      typeInto(PASTED)
      // Well inside the two-second window: the teacher clicked the next block.
      await elapse(300)
      expect(updateCalls).toHaveLength(0)

      unmount()
      await elapse(0)

      expect(updateCalls).toEqual([["b-1", { content: PASTED }]])
      expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ content: PASTED }))
    })

    it("sends nothing when nothing changed — including StrictMode's rehearsal unmount", async () => {
      const { unmount } = renderEditor({}, { strict: true })
      await elapse(100)
      unmount()
      await elapse(0)

      expect(updateCalls).toHaveLength(0)
    })

    it("keeps the block flagged unsaved and says so when the send after collapse fails", async () => {
      updateImpl = () => Promise.reject(new Error("network down"))
      const onUnsavedChange = vi.fn()
      const { unmount } = renderEditor({}, { onUnsavedChange })
      typeInto(PASTED)
      expect(onUnsavedChange).toHaveBeenLastCalledWith(true)

      unmount()
      await elapse(0)

      expect(updateCalls).toHaveLength(1)
      // Never told the parent the text was safe.
      expect(onUnsavedChange).not.toHaveBeenCalledWith(false)
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "The block you closed could not be saved",
          variant: "destructive",
        }),
      )
      // The hook wrote the text down on the same unmount — reopening finds it.
      expect(window.localStorage.getItem(DRAFT_KEY)).toBe(PASTED)
    })
  })

  describe("a hidden tab", () => {
    it("still saves when the timer fires while the teacher is in Word", async () => {
      renderEditor()
      typeInto(PASTED)
      setVisibility("hidden")

      await elapse(2000)

      expect(updateCalls).toEqual([["b-1", { content: PASTED }]])
    })

    it("saves the moment the tab goes to the background, without waiting out the debounce", async () => {
      renderEditor()
      typeInto(PASTED)
      await elapse(200)
      expect(updateCalls).toHaveLength(0)

      setVisibility("hidden")
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"))
      })

      expect(updateCalls).toEqual([["b-1", { content: PASTED }]])
    })

    it("fires a keepalive request when the page itself is going away", async () => {
      renderEditor()
      typeInto(PASTED)

      await act(async () => {
        window.dispatchEvent(new Event("pagehide"))
      })

      expect(keepalivePuts).toHaveLength(1)
      const [url, body, config] = keepalivePuts[0] ?? []
      expect(url).toBe("/blocks/b-1")
      expect(body).toEqual({ content: PASTED })
      expect(config).toMatchObject({ fetchOptions: { keepalive: true } })
    })
  })

  describe("a failed save", () => {
    it("stays visibly unsaved, tells the teacher, and retries until the text lands", async () => {
      let attempts = 0
      updateImpl = (id, data) => {
        attempts += 1
        if (attempts === 1) return Promise.reject(new Error("502"))
        return Promise.resolve({ ...baseBlock, id, content: data.content ?? null })
      }
      renderEditor()
      typeInto(PASTED)

      await elapse(2000)
      expect(updateCalls).toHaveLength(1)
      expect(screen.getByRole("alert")).toHaveTextContent(/not saved on the server yet/i)
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({ title: "Auto-save failed", variant: "destructive" }),
      )
      // Nothing claims the text is safe.
      expect(screen.queryByText("Saved")).toBeNull()

      // First retry after two seconds, without the teacher touching anything.
      await elapse(2000)
      expect(updateCalls).toHaveLength(2)
      expect(updateCalls[1]).toEqual(["b-1", { content: PASTED }])
      expect(screen.getByText("Saved")).toBeInTheDocument()
      expect(screen.queryByRole("alert")).toBeNull()
    })

    it("backs off instead of hammering a server that keeps failing", async () => {
      updateImpl = () => Promise.reject(new Error("502"))
      renderEditor()
      typeInto(PASTED)

      await elapse(2000) // attempt 1
      await elapse(2000) // attempt 2 after 2 s
      await elapse(5000) // attempt 3 after 5 s
      expect(updateCalls).toHaveLength(3)
      // Within the next 5 s nothing: the fourth waits 10 s.
      await elapse(5000)
      expect(updateCalls).toHaveLength(3)
      await elapse(5000)
      expect(updateCalls).toHaveLength(4)
      // The toast is once per streak, not once per retry.
      expect(toast).toHaveBeenCalledTimes(1)
    })
  })

  describe("the local draft", () => {
    it("writes what was pasted into localStorage so a reload or a redirect to /login cannot take it", async () => {
      renderEditor()
      typeInto(PASTED)

      await elapse(500)
      expect(window.localStorage.getItem(DRAFT_KEY)).toBe(PASTED)

      // Once the server has it there is nothing left to protect.
      await elapse(2000)
      expect(updateCalls).toHaveLength(1)
      expect(window.localStorage.getItem(DRAFT_KEY)).toBeNull()
    })

    it("does not write the server's text over a draft it has not offered back yet", async () => {
      window.localStorage.setItem(DRAFT_KEY, PASTED)
      renderEditor()
      await elapse(1000)

      expect(window.localStorage.getItem(DRAFT_KEY)).toBe(PASTED)
    })

    it("offers the draft back when it differs from the server, and saves it when the teacher takes it", async () => {
      window.localStorage.setItem(DRAFT_KEY, PASTED)
      renderEditor()

      expect(screen.getByRole("status")).toHaveTextContent(/unsaved text for this block/i)
      // Neither side was touched silently.
      expect(screen.getByLabelText("content")).toHaveValue(baseBlock.content)

      fireEvent.click(screen.getByRole("button", { name: "Bring back the unsaved text" }))
      expect(screen.getByLabelText("content")).toHaveValue(PASTED)
      expect(screen.queryByRole("status")).toBeNull()

      await elapse(2000)
      expect(updateCalls).toEqual([["b-1", { content: PASTED }]])
    })

    it("lets the teacher keep the server version, and forgets the draft then", async () => {
      window.localStorage.setItem(DRAFT_KEY, PASTED)
      const onUnsavedChange = vi.fn()
      renderEditor({}, { onUnsavedChange })

      fireEvent.click(screen.getByRole("button", { name: "Keep the server version" }))

      expect(screen.queryByRole("status")).toBeNull()
      expect(screen.getByLabelText("content")).toHaveValue(baseBlock.content)
      expect(window.localStorage.getItem(DRAFT_KEY)).toBeNull()
      expect(onUnsavedChange).toHaveBeenLastCalledWith(false)
      await elapse(3000)
      expect(updateCalls).toHaveLength(0)
    })

    it("puts the draft straight back into an empty block and saves it", async () => {
      window.localStorage.setItem(DRAFT_KEY, PASTED)
      renderEditor({ content: "" })

      expect(screen.queryByRole("status")).toBeNull()
      expect(screen.getByLabelText("content")).toHaveValue(PASTED)

      await elapse(2000)
      expect(updateCalls).toEqual([["b-1", { content: PASTED }]])
    })
  })
})
