import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * CSS `capitalize` must never dress a formatted date.
 *
 * `text-transform: capitalize` raises the first letter of EVERY word. English
 * and German survive it because `Intl` already capitalises their month names;
 * Russian and Ukrainian do not:
 *
 *   понедельник, 31 августа  →  Понедельник, 31 Августа
 *   август 2026 г.           →  Август 2026 Г.
 *
 * Both shipped — the dashboard's Today card and the month header inside the
 * calendar popover. The fix is `first-letter:uppercase`, which raises the one
 * letter that is ours to raise.
 *
 * This reads the source rather than the DOM on purpose: jsdom applies no
 * stylesheet, so the wrong class renders identically to the right one in every
 * component test we have. A file that formats a date and also carries the
 * class is the only signal available without a browser.
 */

const SRC = join(__dirname, "..", "..")
const FORMATS_A_DATE = /toLocaleDateString|toLocaleString|Intl\.DateTimeFormat/
const CSS_CAPITALIZE = /className="[^"]*\bcapitalize\b/

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === "__tests__" || entry.name === "node_modules") continue
      yield* walk(full)
    } else if (entry.name.endsWith(".tsx")) {
      yield full
    }
  }
}

describe("formatted dates", () => {
  it("are never dressed with CSS `capitalize`", () => {
    const offenders: string[] = []
    for (const file of walk(SRC)) {
      const source = readFileSync(file, "utf8")
      if (FORMATS_A_DATE.test(source) && CSS_CAPITALIZE.test(source)) {
        offenders.push(file.slice(SRC.length + 1))
      }
    }

    expect(
      offenders,
      `These files format a date and carry CSS \`capitalize\`. In Russian and ` +
        `Ukrainian that renders "31 Августа" and "2026 Г.". Use ` +
        `\`first-letter:uppercase\`.\n  ${offenders.join("\n  ")}`,
    ).toEqual([])
  })
})
