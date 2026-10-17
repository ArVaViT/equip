/**
 * Pictures in pasted HTML (Word, Outlook, another editor) — see
 * `pastedImages.ts`. The pure rewrite first, then the whole path through a
 * real TipTap editor: ProseMirror's own paste logic calls our transform and
 * then our handler, in that order, just as a browser paste does.
 */
import type { ReactNode } from "react"
import { I18nextProvider } from "react-i18next"
import { act, renderHook, waitFor } from "@testing-library/react"
import { Editor } from "@tiptap/core"
import StarterKit from "@tiptap/starter-kit"
import Image from "@tiptap/extension-image"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"

const uploadContentImage = vi.hoisted(() => vi.fn())
const toast = vi.hoisted(() => vi.fn())
vi.mock("@/services/storage", () => ({ storageService: { uploadContentImage } }))
vi.mock("@/lib/toast", () => ({ toast }))

import {
  dataUriToFile,
  htmlHasText,
  preparePastedHtml,
  resetPastedUploads,
  withUploadedImages,
  withUploadedImagesNow,
} from "../pastedImages"
import { useImageUpload } from "../useImageUpload"

// A 1×1 transparent PNG.
const PNG_B64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
const DATA_PNG = `data:image/png;base64,${PNG_B64}`

let blobCounter = 0
const revoked: string[] = []

beforeEach(async () => {
  await i18n.changeLanguage("ru")
  blobCounter = 0
  revoked.length = 0
  // jsdom has no object URLs.
  URL.createObjectURL = vi.fn(() => `blob:test/${++blobCounter}`)
  URL.revokeObjectURL = vi.fn((url: string) => void revoked.push(url))
  uploadContentImage.mockReset()
  toast.mockReset()
  resetPastedUploads()
})

describe("preparePastedHtml", () => {
  it("drops pictures the browser can never open, and counts them", () => {
    const word =
      '<p class=MsoNormal>Урок 1</p><p><img width=200 src="file:///C:/Users/t/AppData/Local/Temp/msohtmlclip1/01/clip_image001.png"></p>' +
      '<p><img src="cid:image002.png@01DA"></p><p><img src="webkit-fake-url://abc/image.png"></p>'
    const out = preparePastedHtml(word)
    expect(out.skipped).toBe(3)
    expect(out.files.size).toBe(0)
    expect(out.html).toContain("Урок 1")
    expect(out.html).not.toContain("<img")
  })

  it("turns a data: picture into a file shown from a blob: URL", () => {
    const out = preparePastedHtml(`<p>до</p><img src="${DATA_PNG}"><p>после</p>`)
    expect(out.skipped).toBe(0)
    expect([...out.files.keys()]).toEqual(["blob:test/1"])
    const file = out.files.get("blob:test/1")!
    expect(file.type).toBe("image/png")
    expect(file.name).toBe("pasted-image-1.png")
    expect(file.size).toBe(atob(PNG_B64).length)
    expect(out.html).toContain('src="blob:test/1"')
    expect(out.html).not.toContain("data:")
  })

  it("drops a picture with no address without counting it", () => {
    const out = preparePastedHtml("<p>x</p><img><img src=\"  \">")
    expect(out.skipped).toBe(0)
    expect(out.html).toBe("<p>x</p>")
  })

  it("leaves pictures that load alone, and HTML without pictures untouched", () => {
    const html = '<p>x</p><img src="https://example.supabase.co/a.png"><img src="/img/course-assets/b.png">'
    const out = preparePastedHtml(html)
    expect(out.skipped).toBe(0)
    expect(out.files.size).toBe(0)
    expect(out.html).toContain("https://example.supabase.co/a.png")
    expect(out.html).toContain("/img/course-assets/b.png")
    expect(preparePastedHtml("<p>текст</p>").html).toBe("<p>текст</p>")
  })

  it("counts a data: URI that is not a picture, or is broken, as skipped", () => {
    expect(preparePastedHtml('<img src="data:text/html;base64,PGI+">').skipped).toBe(1)
    expect(preparePastedHtml('<img src="data:image/png;base64,%%%">').skipped).toBe(1)
    expect(preparePastedHtml('<img src="data:image/png;base64,">').skipped).toBe(1)
  })
})

describe("dataUriToFile / htmlHasText", () => {
  it("reads a percent-encoded SVG as well as base64", () => {
    const file = dataUriToFile("data:image/svg+xml,%3Csvg%2F%3E", 2)
    expect(file?.type).toBe("image/svg+xml")
    expect(file?.name).toBe("pasted-image-3.svgxml")
  })

  it("tells a document from a lone picture", () => {
    expect(htmlHasText('<meta charset="utf-8"><img src="https://x/a.png">')).toBe(false)
    expect(htmlHasText("")).toBe(false)
    expect(htmlHasText("<p>Слово</p><img src=x>")).toBe(true)
  })
})

describe("pasting HTML into the editor", () => {
  let editor: Editor | null = null

  function setup() {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    )
    const { result } = renderHook(() => useImageUpload(), { wrapper })
    editor = new Editor({
      extensions: [StarterKit, Image],
      content: "<p></p>",
      editorProps: {
        handlePaste: (view, event) => result.current.handlePaste(view, event as ClipboardEvent),
        transformPastedHTML: (html) => result.current.transformPastedHTML(html),
      },
    })
    return editor
  }

  /** A paste event the way a browser hands Word's clipboard over. */
  function clipboard(html: string, files: File[] = []): ClipboardEvent {
    const items = files.map((f) => ({ type: f.type, getAsFile: () => f }))
    return {
      clipboardData: {
        getData: (type: string) => (type === "text/html" ? html : ""),
        items,
      },
      preventDefault: vi.fn(),
    } as unknown as ClipboardEvent
  }

  function images(ed: Editor): string[] {
    const srcs: string[] = []
    ed.state.doc.descendants((node) => {
      if (node.type.name === "image") srcs.push(String(node.attrs.src))
    })
    return srcs
  }

  afterEach(() => {
    editor?.destroy()
    editor = null
  })

  it("uploads a data: picture through the editor's upload path and swaps in the stored address", async () => {
    uploadContentImage.mockResolvedValue("https://store.supabase.co/course-assets/p.png")
    const ed = setup()
    act(() => {
      ed.view.pasteHTML(`<p>Глава</p><img src="${DATA_PNG}">`, clipboard(`<p>Глава</p><img src="${DATA_PNG}">`))
    })
    expect(ed.getText()).toContain("Глава")
    expect(images(ed)).toEqual(["blob:test/1"])
    await waitFor(() => expect(images(ed)).toEqual(["https://store.supabase.co/course-assets/p.png"]))
    expect(uploadContentImage).toHaveBeenCalledTimes(1)
    expect((uploadContentImage.mock.calls[0]![0] as File).type).toBe("image/png")
    expect(revoked).toEqual(["blob:test/1"])
    expect(toast).not.toHaveBeenCalled()
  })

  it("removes the picture when its upload fails, and the text stays", async () => {
    uploadContentImage.mockRejectedValue(new Error("network"))
    const ed = setup()
    act(() => {
      ed.view.pasteHTML(`<p>Глава</p><img src="${DATA_PNG}">`, clipboard(`<p>Глава</p><img src="${DATA_PNG}">`))
    })
    await waitFor(() => expect(images(ed)).toEqual([]))
    expect(ed.getText()).toContain("Глава")
    // The upload path's own toast says why.
    expect(toast).toHaveBeenCalledWith(expect.objectContaining({ variant: "destructive" }))
  })

  it("pastes Word's text without a broken picture and says once what to do", () => {
    const ed = setup()
    const html =
      '<p>Первый абзац</p><p><img src="file:///Users/t/Library/clip_image001.png"></p><p><img src="file:///Users/t/Library/clip_image002.png"></p>'
    act(() => {
      ed.view.pasteHTML(html, clipboard(html))
    })
    expect(ed.getText()).toContain("Первый абзац")
    expect(images(ed)).toEqual([])
    expect(uploadContentImage).not.toHaveBeenCalled()
    expect(toast).toHaveBeenCalledTimes(1)
    expect(toast).toHaveBeenCalledWith({ title: i18n.t("editor.toast.pastedImagesSkipped") })
  })

  it("takes the document's words, not the picture of them Word also puts on the clipboard", () => {
    const ed = setup()
    const html = "<p>Текст урока</p>"
    const snapshot = new File([new Uint8Array([1, 2, 3])], "image.png", { type: "image/png" })
    act(() => {
      ed.view.pasteHTML(html, clipboard(html, [snapshot]))
    })
    expect(ed.getText()).toContain("Текст урока")
    expect(uploadContentImage).not.toHaveBeenCalled()
  })

  it("still uploads a lone picture (a screenshot, an image copied from a page)", async () => {
    uploadContentImage.mockResolvedValue("https://store.supabase.co/course-assets/s.png")
    const ed = setup()
    const shot = new File([new Uint8Array([1, 2, 3])], "image.png", { type: "image/png" })
    const html = `<meta charset="utf-8"><img src="${DATA_PNG}">`
    act(() => {
      ed.view.pasteHTML(html, clipboard(html, [shot]))
    })
    await waitFor(() => expect(images(ed)).toEqual(["https://store.supabase.co/course-assets/s.png"]))
    expect(uploadContentImage).toHaveBeenCalledTimes(1)
    expect(uploadContentImage).toHaveBeenCalledWith(shot)
    // The blob: the transform minted for the HTML's copy is let go.
    expect(revoked).toEqual(["blob:test/1"])
  })
})

describe("a save while a pasted picture uploads", () => {
  it("waits for the upload the paste started and saves the stored address", async () => {
    let finish: (url: string) => void = () => {}
    uploadContentImage.mockReturnValue(new Promise((resolve) => (finish = resolve)))
    const wrapper = ({ children }: { children: ReactNode }) => (
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    )
    const { result } = renderHook(() => useImageUpload(), { wrapper })
    const ed = new Editor({
      extensions: [StarterKit, Image],
      content: "<p></p>",
      editorProps: {
        handlePaste: (view, event) => result.current.handlePaste(view, event as ClipboardEvent),
        transformPastedHTML: (html) => result.current.transformPastedHTML(html),
      },
    })
    const html = `<p>Глава</p><img src="${DATA_PNG}">`
    act(() => {
      ed.view.pasteHTML(html, {
        clipboardData: { getData: (t: string) => (t === "text/html" ? html : ""), items: [] },
        preventDefault: vi.fn(),
      } as unknown as ClipboardEvent)
    })
    const taken = ed.getHTML()
    expect(taken).toContain('src="blob:test/1"')
    // The teacher leaves; the editor goes with them.
    ed.destroy()

    const saving = withUploadedImages(taken)
    expect(withUploadedImagesNow(taken)).not.toContain("<img")
    finish("https://store.supabase.co/course-assets/p.png")

    const saved = await saving
    expect(saved).toContain('src="https://store.supabase.co/course-assets/p.png"')
    expect(saved).not.toContain("blob:")
    expect(withUploadedImagesNow(taken)).toBe(saved)
  })

  it("drops a blob: this page never made, and leaves HTML without one untouched", async () => {
    expect(await withUploadedImages('<p>x</p><img src="blob:old/9">')).toBe("<p>x</p>")
    const plain = '<p>x</p><img src="https://example.supabase.co/a.png">'
    expect(await withUploadedImages(plain)).toBe(plain)
  })
})
