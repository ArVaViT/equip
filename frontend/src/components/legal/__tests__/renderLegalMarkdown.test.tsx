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
