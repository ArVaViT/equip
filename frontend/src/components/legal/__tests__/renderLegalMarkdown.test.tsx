import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { renderLegalMarkdown } from "../renderLegalMarkdown"

/**
 * The renderer is small and hand-written, which is the point — it produces
 * React elements, so no HTML string ever exists and there is nothing to
 * sanitise. What it must never do is drop text: a legal document that loses a
 * clause because the renderer did not recognise the syntax is the worst
 * failure this file could have, and it would be silent.
 */
describe("renderLegalMarkdown", () => {
  it("sets headings, paragraphs, bullets and bold", () => {
    render(
      <div>
        {renderLegalMarkdown(
          [
            "# Политика конфиденциальности",
            "",
            "## Что мы храним",
            "",
            "Имя и **адрес электронной почты**.",
            "",
            "- Прочитанные главы",
            "- Ответы на тесты",
          ].join("\n"),
        )}
      </div>,
    )

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Политика конфиденциальности",
    )
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent("Что мы храним")
    expect(screen.getByText("адрес электронной почты").tagName).toBe("STRONG")
    expect(screen.getAllByRole("listitem")).toHaveLength(2)
  })

  it("builds a real table with a header row", () => {
    render(
      <div>
        {renderLegalMarkdown(
          ["| Кто | Что видит |", "|---|---|", "| Supabase | база данных |"].join("\n"),
        )}
      </div>,
    )

    expect(screen.getByRole("columnheader", { name: "Кто" })).toBeInTheDocument()
    expect(screen.getByRole("cell", { name: "Supabase" })).toBeInTheDocument()
    // The `|---|---|` divider is structure, not content, and must not appear.
    expect(screen.queryByText(/---/)).not.toBeInTheDocument()
  })

  it("renders unrecognised syntax as text rather than losing it", () => {
    // A dropped clause is worse than an ugly one.
    render(<div>{renderLegalMarkdown("> Мы не продаём ваши данные.")}</div>)

    expect(screen.getByText(/Мы не продаём ваши данные/)).toBeInTheDocument()
  })

  it("joins a wrapped paragraph back into one", () => {
    render(
      <div>
        {renderLegalMarkdown(["Этот документ описывает,", "какие данные платформа хранит."].join("\n"))}
      </div>,
    )

    expect(
      screen.getByText("Этот документ описывает, какие данные платформа хранит."),
    ).toBeInTheDocument()
  })

  it("keeps two paragraphs apart", () => {
    const { container } = render(
      <div>{renderLegalMarkdown(["Первый абзац.", "", "Второй абзац."].join("\n"))}</div>,
    )

    expect(container.querySelectorAll("p")).toHaveLength(2)
  })
})

describe("the documents point at each other", () => {
  it("renders a cross-reference as a link rather than as its own source", () => {
    render(
      <div>
        {renderLegalMarkdown("Teachers are also bound by the [Teacher Agreement](/teacher-terms).")}
      </div>,
    )
    const link = screen.getByRole("link", { name: "Teacher Agreement" })
    expect(link).toHaveAttribute("href", "/teacher-terms")
    // Until 2026-09-17 this rendered the square brackets, and a reader
    // following a cross-reference was reading Markdown source.
    expect(screen.queryByText(/\[Teacher Agreement\]/)).not.toBeInTheDocument()
  })

  it("leaves an external link as plain text rather than pointing a reader off the platform", () => {
    render(<div>{renderLegalMarkdown("See [somewhere else](https://example.com).")}</div>)
    expect(screen.queryByRole("link")).not.toBeInTheDocument()
  })

  it("keeps bold working next to a link", () => {
    const { container } = render(
      <div>{renderLegalMarkdown("**Counter-notice.** Write to us via the [Terms](/terms).")}</div>,
    )
    expect(container.querySelector("strong")).toHaveTextContent("Counter-notice.")
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms")
  })

  it("numbers the takedown notice, because the count is load-bearing", () => {
    const { container } = render(
      <div>
        {renderLegalMarkdown(
          ["Your notice should contain:", "", "1. Your signature.", "2. The work.", "3. Where it is."].join("\n"),
        )}
      </div>,
    )
    const items = container.querySelectorAll("ol > li")
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent("Your signature.")
  })
})
