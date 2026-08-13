import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { SubmissionDeclaration, type DeclarationState } from "../SubmissionDeclaration"
import { declarationStatement } from "../declarationStatement"
import type { AiPolicy } from "@/types"

const BLANK: DeclarationState = { confirmed: false, usedAi: false, note: "" }

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

function show(policy: AiPolicy, value: DeclarationState = BLANK, onChange = vi.fn()) {
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

  it("carries the policy, an example and the consequences together", () => {
    show("ai_with_disclosure")

    // The three parts are the finding, not a layout choice: the reminder found
    // to reduce cheating in unproctored settings carried all three. Any one
    // alone is a checkbox.
    expect(screen.getByText(/ИИ использовать можно/)).toBeInTheDocument()
    expect(screen.getByText(/Просил перефразировать введение/)).toBeInTheDocument()
    expect(screen.getByText(/Скрытое использование/)).toBeInTheDocument()
  })

  it("says something different where the course forbids it", () => {
    show("ai_forbidden")

    expect(screen.getByText(/ИИ использовать нельзя/)).toBeInTheDocument()
    // And still promises a person rather than an automatic zero.
    expect(screen.getByText(/это разговор/)).toBeInTheDocument()
  })

  it("asks nothing at all where there is no rule", () => {
    const { container } = show("ai_open")

    // A confirmation on a course with no rule trains students to tick past it
    // on the courses that have one.
    expect(container).toBeEmptyDOMElement()
  })

  it("is never pre-ticked", () => {
    show("ai_with_disclosure")

    expect(screen.getByRole("checkbox", { name: /подтверждаю/i })).not.toBeChecked()
  })

  it("asks where and how, once the student says they used it", async () => {
    const onChange = vi.fn()
    show("ai_with_disclosure", { ...BLANK, usedAi: true }, onChange)

    // Their own sentence, next to the essay, tells a teacher more than any
    // detector would — and it is the whole reason disclosure beats a ban.
    expect(screen.getByPlaceholderText(/перефразировать два абзаца/)).toBeInTheDocument()
  })

  it("does not ask about AI use where the course bans it", () => {
    show("ai_forbidden")

    // One checkbox, not two: under a ban the honest declaration is made in the
    // conversation the consequence line promises, not by ticking a box that
    // reads like permission.
    expect(screen.getAllByRole("checkbox")).toHaveLength(1)
  })

  it("reports the tick upward rather than keeping it", async () => {
    const onChange = vi.fn()
    show("ai_with_disclosure", BLANK, onChange)

    await userEvent.click(screen.getByRole("checkbox", { name: /подтверждаю/i }))

    expect(onChange).toHaveBeenCalledWith({ confirmed: true, usedAi: false, note: "" })
  })

  it("builds the stored statement out of what was on the screen", () => {
    const statement = declarationStatement("ai_forbidden", (k) => i18n.t(k))

    // Not a key into a catalogue: what a person agreed to has to survive the
    // catalogue being edited next month.
    expect(statement).toContain(i18n.t("declaration.ai_forbidden.policy"))
    expect(statement).toContain(i18n.t("declaration.ai_forbidden.consequence"))
  })
})
