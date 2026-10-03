import { render, screen } from "@testing-library/react"
import { I18nextProvider } from "react-i18next"
import { MemoryRouter } from "react-router-dom"
import { AxiosError } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n/config"
import { dailyChallengeService } from "@/services/dailyChallenge"
import DailyChallengeArchivePage from "../DailyChallengeArchivePage"

describe("the Daily Challenge archive", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en")
    vi.restoreAllMocks()
    vi.spyOn(dailyChallengeService, "listArchive").mockResolvedValue({ entries: [], next_cursor: null })
  })

  it("does not leave the panel blank for a day that cannot be replayed yet", async () => {
    // A stale or hand-edited ?d= pointing at today or later.
    const err = new AxiosError("not allowed", "ERR_BAD_REQUEST")
    Object.assign(err, {
      response: { status: 400, data: { detail: { code: "daily_challenge.archive_date_not_allowed", message: "x" } } },
    })
    vi.spyOn(dailyChallengeService, "getArchiveQuestion").mockRejectedValue(err)

    render(
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={["/daily-challenge/archive?d=2099-01-01"]}>
          <DailyChallengeArchivePage />
        </MemoryRouter>
      </I18nextProvider>,
    )

    expect(
      await screen.findByText(i18n.t("dailyChallenge.archive.notScheduled.title")),
    ).toBeInTheDocument()
  })
})
