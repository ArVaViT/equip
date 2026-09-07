/**
 * Content that arrives as the reader reaches it.
 *
 * The landing page was entirely static while `motion` sat in the bundle,
 * approved by ADR and used nowhere on the one page built to be read
 * top-to-bottom. `StaggerChildren` covers an entrance on mount; this covers
 * the half below the fold.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { Reveal } from "@/components/motion";

const reducedMotion = vi.fn(() => false);
vi.mock("motion/react", async () => {
  const actual = await vi.importActual<typeof import("motion/react")>("motion/react");
  return { ...actual, useReducedMotion: () => reducedMotion() };
});

describe("Reveal", () => {
  it("renders its content", () => {
    reducedMotion.mockReturnValue(false);
    render(
      <Reveal>
        <p>Читаемый текст</p>
      </Reveal>,
    );
    expect(screen.getByText("Читаемый текст")).toBeInTheDocument();
  });

  it("renders plain markup when motion is not wanted", () => {
    // Not "animates faster" — no wrapper animation at all, which is also
    // what a crawler and a screen reader see.
    reducedMotion.mockReturnValue(true);
    const { container } = render(
      <Reveal className="probe">
        <p>Читаемый текст</p>
      </Reveal>,
    );
    const wrapper = container.querySelector(".probe");
    expect(wrapper?.tagName).toBe("DIV");
    expect(wrapper?.getAttribute("style")).toBeNull();
    expect(screen.getByText("Читаемый текст")).toBeInTheDocument();
  });

  it("renders plain markup where there is no observer to wait for", () => {
    // A reveal starts at opacity 0 and waits to be told it is in view. Where
    // IntersectionObserver does not exist the wait never ends and the section
    // is never shown at all — so the wrapper must not start the animation.
    reducedMotion.mockReturnValue(false);
    const observer = globalThis.IntersectionObserver;
    // @ts-expect-error — deliberately removing it for this case
    delete globalThis.IntersectionObserver;
    try {
      const { container } = render(
        <Reveal className="probe">
          <p>Читаемый текст</p>
        </Reveal>,
      );
      expect(container.querySelector(".probe")?.getAttribute("style")).toBeNull();
      expect(screen.getByText("Читаемый текст")).toBeVisible();
    } finally {
      globalThis.IntersectionObserver = observer;
    }
  });

  it("keeps the content in the DOM even before it is revealed", () => {
    // Hidden is not absent: a crawler and a screen reader must find the text
    // whether or not the observer has fired.
    reducedMotion.mockReturnValue(false);
    render(
      <Reveal>
        <p>Читаемый текст</p>
      </Reveal>,
    );
    expect(screen.getByText("Читаемый текст")).toBeInTheDocument();
  });
});
