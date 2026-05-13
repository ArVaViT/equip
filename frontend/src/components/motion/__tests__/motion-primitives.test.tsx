import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import {
  FadeIn,
  HoverLift,
  PageTransition,
  PressFeedback,
  Reveal,
  StaggerChildren,
} from ".."

function mockPrefersReducedMotion(reduce: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion: reduce"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

afterEach(() => {
  mockPrefersReducedMotion(false)
})

describe("motion primitives — render children", () => {
  it("FadeIn renders children", () => {
    render(<FadeIn>hello fade</FadeIn>)
    expect(screen.getByText("hello fade")).toBeInTheDocument()
  })

  it("StaggerChildren renders all children", () => {
    render(
      <StaggerChildren>
        <span>one</span>
        <span>two</span>
        <span>three</span>
      </StaggerChildren>,
    )
    expect(screen.getByText("one")).toBeInTheDocument()
    expect(screen.getByText("two")).toBeInTheDocument()
    expect(screen.getByText("three")).toBeInTheDocument()
  })

  it("HoverLift renders children", () => {
    render(<HoverLift>liftable</HoverLift>)
    expect(screen.getByText("liftable")).toBeInTheDocument()
  })

  it("PressFeedback renders children", () => {
    render(<PressFeedback>pressable</PressFeedback>)
    expect(screen.getByText("pressable")).toBeInTheDocument()
  })

  it("Reveal renders children", () => {
    render(<Reveal>revealable</Reveal>)
    expect(screen.getByText("revealable")).toBeInTheDocument()
  })

  it("PageTransition renders children", () => {
    render(<PageTransition routeKey="/x">page</PageTransition>)
    expect(screen.getByText("page")).toBeInTheDocument()
  })
})

describe("motion primitives — prefers-reduced-motion", () => {
  it("FadeIn renders plain div when reduced motion is requested", () => {
    mockPrefersReducedMotion(true)
    render(
      <FadeIn className="rm">
        <span>reduced</span>
      </FadeIn>,
    )
    const child = screen.getByText("reduced")
    expect(child.parentElement).toHaveClass("rm")
  })

  it("StaggerChildren renders plain children when reduced motion is requested", () => {
    mockPrefersReducedMotion(true)
    render(
      <StaggerChildren className="rm-wrap">
        <span>a</span>
        <span>b</span>
      </StaggerChildren>,
    )
    expect(screen.getByText("a")).toBeInTheDocument()
    expect(screen.getByText("b")).toBeInTheDocument()
  })

  it("Reveal renders plain div when reduced motion is requested", () => {
    mockPrefersReducedMotion(true)
    render(
      <Reveal className="rm">
        <span>r</span>
      </Reveal>,
    )
    expect(screen.getByText("r")).toBeInTheDocument()
  })
})

describe("motion primitives — className passthrough", () => {
  it("FadeIn applies className", () => {
    render(
      <FadeIn className="fade-cls">
        <span>x</span>
      </FadeIn>,
    )
    expect(screen.getByText("x").parentElement).toHaveClass("fade-cls")
  })

  it("Reveal applies className", () => {
    render(
      <Reveal className="reveal-cls">
        <span>x</span>
      </Reveal>,
    )
    expect(screen.getByText("x").parentElement).toHaveClass("reveal-cls")
  })
})
