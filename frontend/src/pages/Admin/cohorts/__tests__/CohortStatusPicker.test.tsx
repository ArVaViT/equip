import React from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, it, expect, vi } from "vitest"

import i18n from "@/i18n/config"
import { CohortStatusPicker } from "@/pages/Admin/cohorts/CohortStatusPicker"

/**
 * The cohort-status badge IS the status picker — same RoleSelector pattern
 * applied to ``Cohort["status"]``. Observable contract:
 *
 *   1. Current status's localized label is visible (badge text).
 *   2. ``disabled`` collapses to a read-only badge — no trigger.
 *   3. The menu lists statuses in canonical order:
 *      upcoming → active → completed.
 *   4. Picking a different status fires ``onChange(next)``.
 *   5. Picking the current status does NOT fire ``onChange``.
 *   6. The ``ariaLabel`` prop wires through to the trigger.
 *
 * Radix internals (positioning, focus, keyboard) are not retested here.
 */

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

const renderOpts = { wrapper: Wrapper }

describe("CohortStatusPicker", () => {
  it("renders the current status's localized label", async () => {
    await i18n.changeLanguage("en")
    render(<CohortStatusPicker status="active" onChange={vi.fn()} />, renderOpts)
    expect(screen.getByText("Active")).toBeInTheDocument()
  })

  it("renders a clickable trigger when not disabled", () => {
    render(<CohortStatusPicker status="upcoming" onChange={vi.fn()} />, renderOpts)
    expect(screen.getByRole("button")).toBeInTheDocument()
  })

  it("renders no trigger when disabled (read-only badge)", () => {
    render(
      <CohortStatusPicker status="completed" disabled={true} onChange={vi.fn()} />,
      renderOpts,
    )
    expect(screen.queryByRole("button")).toBeNull()
  })

  it("propagates ariaLabel to the trigger", () => {
    render(
      <CohortStatusPicker
        status="upcoming"
        onChange={vi.fn()}
        ariaLabel="Change cohort status"
      />,
      renderOpts,
    )
    expect(
      screen.getByRole("button", { name: "Change cohort status" }),
    ).toBeInTheDocument()
  })

  it("opens the menu showing statuses in canonical order", async () => {
    const user = userEvent.setup()
    await i18n.changeLanguage("en")
    render(<CohortStatusPicker status="upcoming" onChange={vi.fn()} />, renderOpts)

    await user.click(screen.getByRole("button"))

    const items = await screen.findAllByRole("menuitem")
    expect(items.map((i) => i.textContent?.trim())).toEqual([
      "Upcoming",
      "Active",
      "Completed",
    ])
  })

  it("fires onChange when a different status is picked", async () => {
    const user = userEvent.setup()
    await i18n.changeLanguage("en")
    const onChange = vi.fn()
    render(
      <CohortStatusPicker status="upcoming" onChange={onChange} />,
      renderOpts,
    )

    await user.click(screen.getByRole("button"))
    const activeItem = await screen.findByRole("menuitem", { name: "Active" })
    await user.click(activeItem)

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith("active")
  })

  it("does NOT fire onChange when the current status is picked", async () => {
    const user = userEvent.setup()
    await i18n.changeLanguage("en")
    const onChange = vi.fn()
    render(
      <CohortStatusPicker status="active" onChange={onChange} />,
      renderOpts,
    )

    await user.click(screen.getByRole("button"))
    const activeItem = await screen.findByRole("menuitem", { name: "Active" })
    await user.click(activeItem)

    expect(onChange).not.toHaveBeenCalled()
  })

  it("renders the localized label under RU as well as EN", async () => {
    await i18n.changeLanguage("ru")
    render(
      <CohortStatusPicker status="active" onChange={vi.fn()} />,
      renderOpts,
    )
    // RU label is "Активный" / similar — we don't pin the exact string,
    // just assert it's NOT the English one and is non-empty.
    const buttons = screen.queryAllByRole("button")
    const text = buttons[0]?.textContent ?? ""
    expect(text).not.toMatch(/^\s*Active\s*$/i)
    expect(text.trim().length).toBeGreaterThan(0)
  })
})
