import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * The card people see when a link to the site is shared.
 *
 * It sat wrong for a long time and nothing could have noticed: `og:image`
 * pointed at the cover image of a dev.to article — a blue book glyph on a
 * blue gradient, wordless — while the product had moved through two palettes
 * to paper and ink. Every link shared into a church chat showed a card
 * belonging to a different product. The favicon, the touch icon, the wordmark
 * and `theme-color` were all still the violet (#422277) of the palette before
 * this one.
 *
 * Two things are worth asserting and cheap to check: the file is the size the
 * markup claims (an unfurler trusts the tag, not the bytes), and the retired
 * palette does not come back.
 */

const ROOT = join(__dirname, "..", "..")
const INDEX = readFileSync(join(ROOT, "index.html"), "utf8")

/** Width/height out of a JPEG's SOF marker — no image library needed. */
function jpegSize(buffer: Buffer): { width: number; height: number } {
  let offset = 2 // skip SOI
  while (offset < buffer.length) {
    if (buffer[offset] !== 0xff) throw new Error("not a JPEG segment boundary")
    const marker = buffer[offset + 1]!
    const length = buffer.readUInt16BE(offset + 2)
    // SOF0..SOF3, SOF5..SOF7, SOF9..SOF11, SOF13..SOF15 carry the dimensions.
    if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
      return { height: buffer.readUInt16BE(offset + 5), width: buffer.readUInt16BE(offset + 7) }
    }
    offset += 2 + length
  }
  throw new Error("no SOF marker found")
}

describe("the share card", () => {
  it("is the size index.html says it is", () => {
    const declaredWidth = Number(INDEX.match(/og:image:width" content="(\d+)"/)?.[1])
    const declaredHeight = Number(INDEX.match(/og:image:height" content="(\d+)"/)?.[1])
    expect(declaredWidth, "og:image:width missing from index.html").toBeGreaterThan(0)

    const actual = jpegSize(readFileSync(join(ROOT, "public", "og-image.jpg")))

    expect(
      actual,
      `og-image.jpg is ${actual.width}x${actual.height} but the markup promises ` +
        `${declaredWidth}x${declaredHeight}. Rebuild it: node scripts/build-og-image.mjs`,
    ).toEqual({ width: declaredWidth, height: declaredHeight })
  })

  it("carries no colour from the retired violet palette", () => {
    // #422277 violet, #A98FE3 its dark-surface variant, #67A982 the old sage.
    const RETIRED = /#(422277|A98FE3|67A982)/i

    const offenders: string[] = []
    if (RETIRED.test(INDEX)) offenders.push("index.html")
    for (const name of readdirSync(join(ROOT, "public"))) {
      if (!name.endsWith(".svg")) continue
      if (RETIRED.test(readFileSync(join(ROOT, "public", name), "utf8"))) offenders.push(`public/${name}`)
    }

    expect(
      offenders,
      "These carry the pre-monochrome violet. The live tokens are #1E1C1A ink, " +
        "#F8F8F6 paper, #4E6E55 sage.",
    ).toEqual([])
  })
})
