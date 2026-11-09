import { describe, expect, it } from "vitest"
import type { TFunction } from "i18next"
import { formatFileSize } from "../fileSize"

// Echo the key and its values so the test reads which unit was picked.
const t = ((key: string, vars: Record<string, unknown>) => `${key.split(".").pop()}:${Object.values(vars)[0]}`) as unknown as TFunction

describe("formatFileSize", () => {
  it("shows a small Word outline in KB, not as 0,0 MB", () => {
    expect(formatFileSize(16_637, t, "assignment.file")).toBe("sizeKb:16")
  })
  it("shows bytes under 1 KB", () => {
    expect(formatFileSize(400, t, "assignment.file")).toBe("sizeBytes:400")
  })
  it("shows MB from 1 MB up", () => {
    expect(formatFileSize(2 * 1024 * 1024, t, "assignment.file")).toBe("sizeMb:2.0")
  })
})
