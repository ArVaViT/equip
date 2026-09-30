import type { ReactNode } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { I18nextProvider } from "react-i18next"
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import i18n from "@/i18n/config"
import { setDisplayTimeZone, zonedDayKey } from "@/i18n/timeZone"
import type { User } from "@/types"

const updateProfile = vi.fn()
vi.mock("@/services/users", () => ({ usersService: { updateProfile: (...a: unknown[]) => updateProfile(...a) } }))
vi.mock("@/lib/toast", () => ({ toast: vi.fn() }))

const applyUser = vi.fn()
let currentUser: User
vi.mock("@/context/useAuth", () => ({ useAuth: () => ({ user: currentUser, applyUser }) }))

import { PersonalDetailsCard } from "../PersonalDetailsCard"
import { TimeZoneSetting } from "../TimeZoneSetting"

function Wrapper({ children }: { children: ReactNode }) {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
}

const baseUser: User = {
  id: "u1",
  email: "student@example.com",
  full_name: "Иван",
  avatar_url: null,
  role: "student",
  preferred_locale: "ru",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  time_zone: "America/Indiana/Indianapolis",
  time_zone_source: "detected",
  phone: null,
  birth_date: null,
  country_code: null,
  region: null,
  city: null,
  church: null,
}

describe("personal details", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterAll(async () => {
    await i18n.changeLanguage("en")
  })
  beforeEach(() => {
    vi.clearAllMocks()
    currentUser = { ...baseUser }
  })

  it("shows the phone but will not let anyone type into it", () => {
    render(<PersonalDetailsCard />, { wrapper: Wrapper })
    expect(screen.getByLabelText("Телефон")).toBeDisabled()
    expect(screen.getByText(/после подтверждения по SMS/)).toBeInTheDocument()
  })

  it("saves only what the person may write, trimmed, and never the phone", async () => {
    const user = userEvent.setup()
    updateProfile.mockResolvedValue({ ...baseUser, city: "Андерсон", church: "Благодать", birth_date: "1990-05-01" })
    render(<PersonalDetailsCard />, { wrapper: Wrapper })
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled()

    await user.type(screen.getByLabelText("Город"), "  Андерсон ")
    await user.type(screen.getByLabelText("Церковь или община"), "Благодать")
    await user.type(screen.getByLabelText("Дата рождения"), "1990-05-01")
    await user.click(screen.getByRole("button", { name: "Сохранить" }))

    await waitFor(() => expect(updateProfile).toHaveBeenCalledTimes(1))
    const payload = updateProfile.mock.calls[0]![0] as Record<string, unknown>
    expect(payload).toEqual({
      birth_date: "1990-05-01",
      country_code: null,
      region: null,
      city: "Андерсон",
      church: "Благодать",
    })
    expect(payload).not.toHaveProperty("phone")
  })

  it("bounds the birth date by today in the profile's zone, not the browser's", () => {
    // UTC+14: for most of the day its date is not the test machine's.
    setDisplayTimeZone("Pacific/Kiritimati")
    try {
      render(<PersonalDetailsCard />, { wrapper: Wrapper })
      expect(screen.getByLabelText("Дата рождения")).toHaveAttribute("max", zonedDayKey(new Date(), "Pacific/Kiritimati"))
    } finally {
      setDisplayTimeZone(null)
    }
  })

  it("refuses a birth date in the future before asking the server", async () => {
    const user = userEvent.setup()
    render(<PersonalDetailsCard />, { wrapper: Wrapper })
    await user.type(screen.getByLabelText("Дата рождения"), "2999-01-01")
    expect(screen.getByText(/между 1900 годом и сегодняшним днём/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled()
  })
})

describe("time zone setting", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })
  afterAll(async () => {
    await i18n.changeLanguage("en")
    setDisplayTimeZone(null)
  })

  it("says the zone follows the device until the person chooses one", () => {
    currentUser = { ...baseUser, time_zone_source: "detected" }
    render(<TimeZoneSetting />, { wrapper: Wrapper })
    expect(screen.getByText(/Определяется по этому устройству/)).toBeInTheDocument()
  })

  it("says it is the person's own choice once chosen", () => {
    currentUser = { ...baseUser, time_zone: "Europe/Berlin", time_zone_source: "chosen" }
    setDisplayTimeZone("Europe/Berlin")
    render(<TimeZoneSetting />, { wrapper: Wrapper })
    expect(screen.getByText(/Выбран вами/)).toBeInTheDocument()
    expect(screen.getByRole("combobox", { name: "Часовой пояс" })).toHaveTextContent("Europe/Berlin")
  })
})
