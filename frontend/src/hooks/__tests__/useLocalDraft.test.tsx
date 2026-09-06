import { useState } from "react"
import { act, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useLocalDraft } from "../useLocalDraft"

const KEY = "equip.draft.assignment.student-1.a-1"

function Harness({ storageKey = KEY as string | null }: { storageKey?: string | null }) {
  const [value, setValue] = useState("")
  const { restored, savedAt, clear } = useLocalDraft(storageKey, value, { delay: 0 })
  return (
    <div>
      <textarea aria-label="essay" value={value} onChange={(e) => setValue(e.target.value)} />
      <button onClick={() => setValue(restored ?? "")}>restore</button>
      <button onClick={clear}>clear</button>
      <span data-testid="saved">{savedAt === null ? "no" : "yes"}</span>
      <span data-testid="restored">{restored ?? ""}</span>
    </div>
  )
}

/**
 * Replaces `window.localStorage` wholesale rather than spying on its methods.
 *
 * Under this Node build `window.localStorage` is not the plain jsdom object a
 * `vi.spyOn` would patch — the spy installs cleanly and then never fires, so
 * the "storage throws" test passes for the wrong reason and proves nothing.
 * Swapping the property is the only interception that actually holds.
 */
function swapStorage(partial: Partial<Storage>) {
  const stub = {
    getItem: () => null,
    setItem: () => undefined,
    removeItem: () => undefined,
    clear: () => undefined,
    key: () => null,
    length: 0,
    ...partial,
  } as Storage
  Object.defineProperty(window, "localStorage", { configurable: true, value: stub })
}

describe("useLocalDraft", () => {
  const real = window.localStorage

  beforeEach(() => {
    Object.defineProperty(window, "localStorage", { configurable: true, value: real })
    window.localStorage.clear()
    vi.restoreAllMocks()
  })
  afterEach(() => {
    Object.defineProperty(window, "localStorage", { configurable: true, value: real })
    window.localStorage.clear()
  })

  it("writes what was typed so a reload cannot take it", async () => {
    render(<Harness />)
    await userEvent.type(screen.getByLabelText("essay"), "Деяния 2")

    await waitFor(() => expect(window.localStorage.getItem(KEY)).toBe("Деяния 2"))
    expect(screen.getByTestId("saved")).toHaveTextContent("yes")
  })

  it("offers back what a previous session left behind", async () => {
    window.localStorage.setItem(KEY, "написано вчера")
    render(<Harness />)

    await waitFor(() => expect(screen.getByTestId("restored")).toHaveTextContent("написано вчера"))
  })

  it("does not offer a draft over text that is already on screen", async () => {
    // Restoring into a non-empty field would overwrite something newer — the
    // resubmission of a returned assignment, say, already populated by its own
    // load. Silence is correct here.
    window.localStorage.setItem(KEY, "старое")
    function Prefilled() {
      const [value] = useState("уже здесь")
      const { restored } = useLocalDraft(KEY, value, { delay: 0 })
      return <span data-testid="restored">{restored ?? "none"}</span>
    }
    render(<Prefilled />)

    await waitFor(() => expect(screen.getByTestId("restored")).toHaveTextContent("none"))
  })

  it("clears the draft when asked, which is what a successful submit does", async () => {
    window.localStorage.setItem(KEY, "черновик")
    render(<Harness />)
    await userEvent.click(screen.getByRole("button", { name: "clear" }))

    await waitFor(() => expect(window.localStorage.getItem(KEY)).toBeNull())
  })

  it("removes the entry when the field is emptied rather than storing nothing", async () => {
    render(<Harness />)
    const field = screen.getByLabelText("essay")
    await userEvent.type(field, "x")
    await waitFor(() => expect(window.localStorage.getItem(KEY)).toBe("x"))
    await userEvent.clear(field)

    await waitFor(() => expect(window.localStorage.getItem(KEY)).toBeNull())
  })

  it("writes nothing at all when there is no user to scope the key to", async () => {
    const setItem = vi.fn()
    swapStorage({ setItem })
    render(<Harness storageKey={null} />)
    await userEvent.type(screen.getByLabelText("essay"), "аноним")

    await waitFor(() => expect(screen.getByLabelText("essay")).toHaveValue("аноним"))
    expect(setItem).not.toHaveBeenCalled()
  })

  it("keeps the student typing when storage throws", async () => {
    // Private mode, a full quota, a locked-down profile. None of them is a
    // reason to interrupt somebody writing an essay.
    swapStorage({
      setItem: () => {
        throw new DOMException("QuotaExceededError")
      },
    })
    render(<Harness />)
    await userEvent.type(screen.getByLabelText("essay"), "всё равно пишу")

    expect(screen.getByLabelText("essay")).toHaveValue("всё равно пишу")
    await waitFor(() => expect(screen.getByTestId("saved")).toHaveTextContent("no"))
  })
})

describe("useLocalDraft — the last half-second and existing content", () => {
  const real = window.localStorage

  beforeEach(() => {
    Object.defineProperty(window, "localStorage", { configurable: true, value: real })
    window.localStorage.clear()
  })
  afterEach(() => {
    Object.defineProperty(window, "localStorage", { configurable: true, value: real })
    window.localStorage.clear()
    vi.useRealTimers()
  })

  function Controlled({ value, restoreInto }: { value: string; restoreInto?: "empty" | "any" }) {
    const { restored } = useLocalDraft(KEY, value, { delay: 500, restoreInto })
    return <span data-testid="restored">{restored ?? "none"}</span>
  }

  it("writes the value on unmount even inside the debounce window", () => {
    vi.useFakeTimers()
    const { rerender, unmount } = render(<Controlled value="" />)
    rerender(<Controlled value="набрано и сразу закрыто" />)
    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(window.localStorage.getItem(KEY)).toBeNull()

    unmount()

    expect(window.localStorage.getItem(KEY)).toBe("набрано и сразу закрыто")
  })

  it("writes the value when the page is hidden, before any timer gets a chance", () => {
    vi.useFakeTimers()
    const { rerender } = render(<Controlled value="" />)
    rerender(<Controlled value="вкладку закрывают" />)

    act(() => {
      window.dispatchEvent(new Event("pagehide"))
    })

    expect(window.localStorage.getItem(KEY)).toBe("вкладку закрывают")
  })

  it("does not write the mount value at all — that would overwrite a waiting draft", () => {
    vi.useFakeTimers()
    window.localStorage.setItem(KEY, "черновик из упавшей вкладки")
    const { unmount } = render(<Controlled value="то, что на сервере" restoreInto="any" />)
    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(window.localStorage.getItem(KEY)).toBe("черновик из упавшей вкладки")

    unmount()
    expect(window.localStorage.getItem(KEY)).toBe("черновик из упавшей вкладки")
  })

  it("with restoreInto: any, offers a draft that differs from the text already on screen", async () => {
    window.localStorage.setItem(KEY, "уже с новым абзацем")
    render(<Controlled value="старый текст" restoreInto="any" />)

    await waitFor(() => expect(screen.getByTestId("restored")).toHaveTextContent("уже с новым абзацем"))
  })

  it("with restoreInto: any, stays silent when the draft is exactly what is on screen", async () => {
    window.localStorage.setItem(KEY, "одно и то же")
    render(<Controlled value="одно и то же" restoreInto="any" />)
    await act(async () => {})

    expect(screen.getByTestId("restored")).toHaveTextContent("none")
  })

  it("does not put a cleared value back into storage on unmount", async () => {
    function ClearOnClick() {
      const [value, setValue] = useState("")
      const { clear } = useLocalDraft(KEY, value, { delay: 0 })
      return (
        <div>
          <textarea aria-label="essay" value={value} onChange={(e) => setValue(e.target.value)} />
          <button onClick={clear}>clear</button>
        </div>
      )
    }
    const { unmount } = render(<ClearOnClick />)
    await userEvent.type(screen.getByLabelText("essay"), "отправлено")
    await waitFor(() => expect(window.localStorage.getItem(KEY)).toBe("отправлено"))
    await userEvent.click(screen.getByRole("button", { name: "clear" }))
    expect(window.localStorage.getItem(KEY)).toBeNull()

    unmount()

    expect(window.localStorage.getItem(KEY)).toBeNull()
  })
})
