import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { SubmissionDeclaration, type DeclarationState } from "../SubmissionDeclaration"
import { BLANK_DECLARATION, declarationStatement } from "../declarationStatement"
import type { AiPolicy } from "@/types"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function show(policy: AiPolicy, value: DeclarationState = BLANK_DECLARATION, onChange = vi.fn()) {
  const result = render(
    <SubmissionDeclaration policy={policy} value={value} onChange={onChange} />,
    { wrapper: Wrapper },
  )
  return { ...result, onChange }
}

describe("SubmissionDeclaration", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
  })

  it("is one line of rule and two answers", () => {
    show("ai_with_disclosure")

    // Three paragraphs and two checkboxes were read by nobody and handed in
    // by nobody. The rule, and the one thing only the student can answer.
    expect(screen.getByText(/ИИ использовать можно/)).toBeInTheDocument()
    expect(screen.getAllByRole("radio")).toHaveLength(2)
    expect(screen.getByRole("radio", { name: "Без ИИ" })).toBeInTheDocument()
    expect(screen.getByRole("radio", { name: "С ИИ" })).toBeInTheDocument()
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument()
  })

  it("says something different where the course forbids it", () => {
    show("ai_forbidden")

    expect(screen.getByText(/ИИ использовать нельзя/)).toBeInTheDocument()
    // Both answers stay: a student who used it where it is banned is telling
    // the truth about a rule they broke, and the server records that.
    expect(screen.getAllByRole("radio")).toHaveLength(2)
  })

  it("asks nothing at all where there is no rule", () => {
    const { container } = show("ai_open")

    // A question on a course with no rule trains students to tap past it on
    // the courses that have one.
    expect(container).toBeEmptyDOMElement()
  })

  it("is never pre-answered", () => {
    show("ai_with_disclosure")

    for (const radio of screen.getAllByRole("radio")) {
      expect(radio).toHaveAttribute("aria-checked", "false")
    }
  })

  it("reports the answer upward rather than keeping it", async () => {
    const onChange = vi.fn()
    show("ai_with_disclosure", BLANK_DECLARATION, onChange)

    await userEvent.click(screen.getByRole("radio", { name: "С ИИ" }))

    expect(onChange).toHaveBeenCalledWith({ aiUse: "assisted", note: "" })
  })

  it("asks what for, once the student says they used it, where the course wants to know", () => {
    show("ai_with_disclosure", { aiUse: "assisted", note: "" })

    // Their own sentence, next to the essay, tells a teacher more than any
    // detector would — and it is the whole reason disclosure beats a ban.
    expect(screen.getByRole("textbox", { name: "Для чего?" })).toBeInTheDocument()
  })

  it("does not ask what for before the answer, nor under a ban", () => {
    show("ai_with_disclosure")
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()

    show("ai_forbidden", { aiUse: "assisted", note: "" })
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  })

  it("builds the stored statement out of what was on the screen", () => {
    const statement = declarationStatement("ai_forbidden", "none", (k) => i18n.t(k))

    // Not a key into a catalogue: what a person agreed to has to survive the
    // catalogue being edited next month. The rule, their answer, and the
    // sentence above the button that makes pressing it the confirmation.
    expect(statement.split("\n")).toEqual([
      i18n.t("declaration.ai_forbidden.rule"),
      i18n.t("declaration.withoutAi"),
      i18n.t("declaration.bySubmitting"),
    ])
    expect(declarationStatement("ai_with_disclosure", "assisted", (k) => i18n.t(k))).toContain("С ИИ")
  })
})
