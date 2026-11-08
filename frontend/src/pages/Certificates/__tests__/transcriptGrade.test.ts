/** The transcript reads the grade off the certificate's snapshot, and only off it. */
import { describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import type { Certificate } from "@/types"
import { mainSymbolScheme, transcriptGrade } from "../transcriptGrade"

const t = (key: string) => i18n.t(key, { lng: "ru" })
const cert = (over: Partial<Certificate>) => ({ status: "approved", ...over }) as Certificate

describe("transcriptGrade", () => {
  it.each([
    ["letter symbol", { grading_scheme: "letter", official_code: "A", graded_via: "computed" }, "A"],
    ["five-point with its word", { grading_scheme: "five_point", official_code: "5", graded_via: "computed" }, "5 (excellent)"],
    ["percent as a number", { grading_scheme: "percent", official_score: "88.50", graded_via: "computed" }, "88.50%"],
    ["pass/fail as a pass", { grading_scheme: "pass_fail", official_score: "40.00", graded_via: "computed" }, "Pass"],
    ["issued on completion", { grading_scheme: "letter", graded_via: "completion" }, "Completed"],
    ["issued before snapshots", {}, "Completed"],
  ] as const)("%s", (_name, over, expected) => {
    // English in every interface language: the transcript is a document.
    expect(transcriptGrade(cert(over as Partial<Certificate>), t).text).toBe(expected)
  })

  it("names the scale most of the sheet is in, letter on a tie", () => {
    const g = (scheme: "letter" | "five_point" | null) => ({ text: "", symbolScheme: scheme })
    expect(mainSymbolScheme([g("five_point"), g("five_point"), g("letter")])).toBe("five_point")
    expect(mainSymbolScheme([g("five_point"), g("letter")])).toBe("letter")
    expect(mainSymbolScheme([g(null)])).toBeNull()
  })
})
