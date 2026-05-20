import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { describe, expect, it } from "vitest"
import i18n from "@/i18n/config"
import { WelcomeCard } from "../WelcomeCard"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("WelcomeCard", () => {
  it("renders the title as a real <h2> heading", () => {
    render(<WelcomeCard title="Welcome to Equip" />, { wrapper: Wrapper })
    // Screen readers should land on a real heading — not a styled <span>
    // or <p>. The editorial title is the landmark of the welcome moment.
    expect(
      screen.getByRole("heading", { level: 2, name: /welcome to equip/i }),
    ).toBeInTheDocument()
  })

  it("renders eyebrow + description when supplied", () => {
    render(
      <WelcomeCard
        eyebrow="Welcome"
        title="Title"
        description="Some warm prose."
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText("Welcome")).toBeInTheDocument()
    expect(screen.getByText("Some warm prose.")).toBeInTheDocument()
  })

  it("omits eyebrow and description nodes when not supplied", () => {
    const { container } = render(<WelcomeCard title="Title only" />, {
      wrapper: Wrapper,
    })
    // Only the sage rule (one <span>) + the heading. No empty <p> tags
    // should render when the optional props are absent — otherwise the
    // surface starts to drift toward the bloated tour-style.
    expect(container.querySelectorAll("p")).toHaveLength(0)
  })

  it("renders the action slot beneath the body", () => {
    render(
      <WelcomeCard
        title="Title"
        action={<button type="button">Browse</button>}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByRole("button", { name: /browse/i })).toBeInTheDocument()
  })
})
