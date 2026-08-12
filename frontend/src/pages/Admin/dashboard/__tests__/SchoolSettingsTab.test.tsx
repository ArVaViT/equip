import type { ReactNode } from "react"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { adminService } from "@/services/admin"
import { SchoolSettingsTab } from "../SchoolSettingsTab"
import type { OrgSettings } from "@/types"

function settings(over: Partial<OrgSettings> = {}): OrgSettings {
  return {
    school_name_ru: "Библейская школа «Слово»",
    school_name_en: "Word Bible School",
    city: "Kyiv",
    default_grading_scheme: "letter",
    default_pass_threshold: "70.00",
    grade_bands: { letter: [[90, "A"], [80, "B"], [70, "C"], [60, "D"], [0, "F"]] },
    updated_at: "2026-08-12T09:00:00Z",
    updated_by: null,
    ...over,
  }
}

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

describe("SchoolSettingsTab", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru")
    vi.restoreAllMocks()
  })

  it("shows what will be printed on the documents", async () => {
    vi.spyOn(adminService, "getOrgSettings").mockResolvedValue(settings())
    render(<SchoolSettingsTab />, { wrapper: Wrapper })

    expect(await screen.findByDisplayValue("Word Bible School")).toBeInTheDocument()
    expect(screen.getByDisplayValue("Kyiv")).toBeInTheDocument()
  })

  it("sends only the identity fields, never the grading scale", async () => {
    vi.spyOn(adminService, "getOrgSettings").mockResolvedValue(settings())
    const update = vi.spyOn(adminService, "updateOrgSettings").mockResolvedValue(settings({ city: "Lviv" }))
    render(<SchoolSettingsTab />, { wrapper: Wrapper })
    const city = await screen.findByDisplayValue("Kyiv")

    await userEvent.clear(city)
    await userEvent.type(city, "Lviv")
    await userEvent.click(screen.getByRole("button", { name: /Сохранить/i }))

    // A typo fix that resends the whole object is a typo fix that can wipe the
    // school's scale — the one field here that silently re-labels every grade.
    expect(update).toHaveBeenCalledWith({
      school_name_ru: "Библейская школа «Слово»",
      school_name_en: "Word Bible School",
      city: "Lviv",
    })
  })

  it("sends null rather than an empty name onto a document", async () => {
    vi.spyOn(adminService, "getOrgSettings").mockResolvedValue(settings())
    const update = vi.spyOn(adminService, "updateOrgSettings").mockResolvedValue(settings())
    render(<SchoolSettingsTab />, { wrapper: Wrapper })
    const city = await screen.findByDisplayValue("Kyiv")

    await userEvent.clear(city)
    await userEvent.click(screen.getByRole("button", { name: /Сохранить/i }))

    expect(update.mock.calls[0]?.[0]?.city).toBeNull()
  })

  it("says which scheme the school grades on without offering to change it here", async () => {
    vi.spyOn(adminService, "getOrgSettings").mockResolvedValue(settings())
    render(<SchoolSettingsTab />, { wrapper: Wrapper })

    expect(await screen.findByText(/буквенная/)).toBeInTheDocument()
    expect(screen.getByText(/70/)).toBeInTheDocument()
  })
})
