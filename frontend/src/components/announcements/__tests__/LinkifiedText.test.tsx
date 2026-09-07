import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { LinkifiedText } from "@/components/announcements/LinkifiedText"
import { linkifySegments } from "@/components/announcements/linkify"

describe("linkifySegments", () => {
  it("leaves text without an address as one plain run", () => {
    expect(linkifySegments("Занятия завтра не будет")).toEqual([
      { kind: "text", value: "Занятия завтра не будет" },
    ])
  })

  it("finds an address in the middle of a sentence", () => {
    expect(linkifySegments("Встречаемся тут: https://zoom.us/j/123?pwd=a&b в 19:00")).toEqual([
      { kind: "text", value: "Встречаемся тут: " },
      { kind: "link", value: "https://zoom.us/j/123?pwd=a&b" },
      { kind: "text", value: " в 19:00" },
    ])
  })

  it("does not carry sentence punctuation into the address", () => {
    expect(linkifySegments("См. https://example.org/a. Потом https://example.org/b, и всё.")).toEqual([
      { kind: "text", value: "См. " },
      { kind: "link", value: "https://example.org/a" },
      { kind: "text", value: ". Потом " },
      { kind: "link", value: "https://example.org/b" },
      { kind: "text", value: ", и всё." },
    ])
  })

  it("keeps a closing bracket that the address itself opened", () => {
    expect(linkifySegments("https://ru.wikipedia.org/wiki/Деяния_(книга)")).toEqual([
      { kind: "link", value: "https://ru.wikipedia.org/wiki/Деяния_(книга)" },
    ])
    expect(linkifySegments("(см. https://example.org/x)")).toEqual([
      { kind: "text", value: "(см. " },
      { kind: "link", value: "https://example.org/x" },
      { kind: "text", value: ")" },
    ])
  })

  it("stops at the quote marks of every served language", () => {
    expect(linkifySegments("ссылка «https://example.org/x» и „https://example.org/y“")).toEqual([
      { kind: "text", value: "ссылка «" },
      { kind: "link", value: "https://example.org/x" },
      { kind: "text", value: "» и „" },
      { kind: "link", value: "https://example.org/y" },
      { kind: "text", value: "“" },
    ])
  })

  it("only recognises http and https", () => {
    expect(linkifySegments("javascript:alert(1) ftp://x.y mailto:a@b.c")).toEqual([
      { kind: "text", value: "javascript:alert(1) ftp://x.y mailto:a@b.c" },
    ])
  })
})

describe("LinkifiedText", () => {
  it("renders an address as a link that opens in a new tab without a handle back", () => {
    render(<LinkifiedText text="Комната: https://zoom.us/j/1 — ждём." />)
    const link = screen.getByRole("link", { name: "https://zoom.us/j/1" })
    expect(link).toHaveAttribute("href", "https://zoom.us/j/1")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
    expect(screen.getByText(/Комната:/)).toBeInTheDocument()
    expect(screen.getByText(/— ждём\./)).toBeInTheDocument()
  })

  it("renders markup as text, never as elements", () => {
    const { container } = render(<LinkifiedText text="<b>жирный</b> и <img src=x onerror=alert(1)>" />)
    expect(container.querySelector("b")).toBeNull()
    expect(container.querySelector("img")).toBeNull()
    expect(container.textContent).toBe("<b>жирный</b> и <img src=x onerror=alert(1)>")
  })
})
