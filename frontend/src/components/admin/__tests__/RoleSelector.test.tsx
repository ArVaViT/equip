import React from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { describe, it, expect, vi } from "vitest"

import i18n from "@/i18n/config"
import { RoleSelector } from "@/components/admin/RoleSelector"

/**
 * The role badge IS the role picker. ``RoleSelector`` rolls four
 * affordances into one Radix ``DropdownMenu`` + ``Badge`` pair, so
 * the observable contract is:
 *
 *   1. The current role's i18n label is always visible (badge text).
 *   2. ``disabled`` collapses the affordance to a read-only badge —
 *      no dropdown trigger, no chevron.
 *   3. Opening the menu reveals all four roles in canonical order:
 *      student → pending_teacher → teacher → admin.
 *   4. Picking a different role fires ``onChange(nextRole)``.
 *   5. Picking the already-selected role does NOT fire ``onChange``
 *      (matches the ``if (!selected) onChange(value)`` guard).
 *   6. The ``ariaLabel`` prop wires through to the trigger so AT can
 *      announce the user the action targets.
 *
 * Tests deliberately don't reach into Radix internals — the menu's
 * positioning, focus management, and keyboard handling are owned by
 * Radix and have their own coverage.
 */

function Wrapper({ children }: { children: React.ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

const renderOpts = { wrapper: Wrapper }

describe("RoleSelector", () => {
  it("renders the current role's localized label", async () => {
    render(<RoleSelector role="teacher" onChange={vi.fn()} />, renderOpts)
    // ``Teacher`` for EN; the i18n config falls back to EN when RU is
    // missing, so this is locale-independent in this test setup.
    await i18n.changeLanguage("en")
    expect(screen.getByText("Teacher")).toBeInTheDocument()
  })

  it("renders a chevron + clickable trigger when not disabled", () => {
    render(<RoleSelector role="student" onChange={vi.fn()} />, renderOpts)
    // Trigger is the <button> wrapping the badge.
    expect(screen.getByRole("button")).toBeInTheDocument()
  })

  it("renders no trigger when disabled (read-only badge)", () => {
    render(
      <RoleSelector role="admin" disabled={true} onChange={vi.fn()} />,
      renderOpts,
    )
    expect(screen.queryByRole("button")).toBeNull()
  })

  it("propagates ariaLabel to the trigger", () => {
    render(
      <RoleSelector
        role="student"
        onChange={vi.fn()}
        ariaLabel="Change role for Jane Doe"
      />,
      renderOpts,
    )
    expect(
      screen.getByRole("button", { name: "Change role for Jane Doe" }),
    ).toBeInTheDocument()
  })

  it("opens the menu showing all four roles in canonical order", async () => {
    const user = userEvent.setup()
    await i18n.changeLanguage("en")
    render(<RoleSelector role="student" onChange={vi.fn()} />, renderOpts)

    await user.click(screen.getByRole("button"))

    const items = await screen.findAllByRole("menuitem")
    expect(items.map((i) => i.textContent?.trim())).toEqual([
      "Student",
      "Pending Teacher",
      "Teacher",
      "Admin",
    ])
  })

  it("fires onChange when a different role is picked", async () => {
    const user = userEvent.setup()
    await i18n.changeLanguage("en")
    const onChange = vi.fn()
    render(<RoleSelector role="student" onChange={onChange} />, renderOpts)

    await user.click(screen.getByRole("button"))
    const teacherItem = await screen.findByRole("menuitem", { name: "Teacher" })
    await user.click(teacherItem)

    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith("teacher")
  })

  it("does NOT fire onChange when the current role is picked", async () => {
    const user = userEvent.setup()
    await i18n.changeLanguage("en")
    const onChange = vi.fn()
    render(<RoleSelector role="teacher" onChange={onChange} />, renderOpts)

    await user.click(screen.getByRole("button"))
    const teacherItem = await screen.findByRole("menuitem", { name: "Teacher" })
    await user.click(teacherItem)

    expect(onChange).not.toHaveBeenCalled()
  })

  it("renders the localized label under RU as well as EN", async () => {
    await i18n.changeLanguage("ru")
    render(<RoleSelector role="pending_teacher" onChange={vi.fn()} />, renderOpts)
    // The RU label is "Преподаватель на проверке" / "Ожидающий…" —
    // we don't pin the exact string (translation may evolve), just
    // assert it's NOT the English one and is non-empty.
    const buttons = screen.queryAllByRole("button")
    const text = buttons[0]?.textContent ?? ""
    expect(text).not.toMatch(/Pending Teacher/i)
    expect(text.trim().length).toBeGreaterThan(0)
  })
})
