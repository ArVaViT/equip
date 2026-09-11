import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { LinkifiedText } from "../LinkifiedText"

/**
 * A description is a free text box and a link is what people put in free
 * text boxes — the first teacher on this platform typed his Zoom address
 * there. Printed as bare text it is a link nobody can follow: on a phone
 * the student selects the string by hand and pastes it elsewhere.
 *
 * The text is never markup. Only whole web addresses become anchors, by
 * the same test the meeting-link field uses, so a `javascript:` value in
 * a description stays a word on the page.
 */
describe("LinkifiedText", () => {
  it("turns a web address into a link you can follow", () => {
    render(<LinkifiedText text="Подключайтесь: https://us02web.zoom.us/j/4959692097" />)
    const link = screen.getByRole("link", { name: "https://us02web.zoom.us/j/4959692097" })
    expect(link).toHaveAttribute("href", "https://us02web.zoom.us/j/4959692097")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link.getAttribute("rel")).toContain("noopener")
  })

  it("leaves the sentence's punctuation out of the link", () => {
    render(<LinkifiedText text="Ссылка здесь: https://zoom.us/j/1." />)
    expect(screen.getByRole("link")).toHaveAttribute("href", "https://zoom.us/j/1")
    expect(screen.getByText(/\.$/)).toBeInTheDocument()
  })

  it("keeps a password in the query intact", () => {
    render(<LinkifiedText text="https://zoom.us/j/85?pwd=aB3.dEf" />)
    expect(screen.getByRole("link")).toHaveAttribute("href", "https://zoom.us/j/85?pwd=aB3.dEf")
  })

  it.each([
    ["a dangerous scheme", "javascript:alert(1)"],
    ["a host in disguise", "https://zoom.us@evil.com/j/1"],
    ["an address with no scheme", "zoom.us/j/123"],
    ["a path on this site", "/courses/1"],
    ["ordinary prose", "Занятие в субботу утром"],
  ])("prints %s as text rather than a link", (_label, text) => {
    render(<LinkifiedText text={text} />)
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
    expect(screen.getByText(text, { exact: false })).toBeInTheDocument()
  })

  it("links every address in a line, not only the first", () => {
    render(<LinkifiedText text="Зум https://a.example/1 и записи https://b.example/2" />)
    expect(screen.getAllByRole("link")).toHaveLength(2)
  })
})
