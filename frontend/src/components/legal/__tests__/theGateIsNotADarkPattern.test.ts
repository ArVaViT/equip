import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import en from "@/i18n/locales/en.json"
import ru from "@/i18n/locales/ru.json"
import de from "@/i18n/locales/de.json"
import uk from "@/i18n/locales/uk.json"

/**
 * Two properties of the blocking consent screens, pinned because both were
 * wrong and both are the kind of wrong that is invisible in review.
 *
 * **The button has to say what the click does.** It said "Continue". In
 * Sgouros v. TransUnion the Seventh Circuit — ours — held against exactly
 * that: a button whose label describes navigation rather than assent is a
 * button somebody can press without agreeing to anything. "Accept and
 * continue" costs one word and says the true thing.
 *
 * **A link has to look like a link when nobody is pointing at it.** The
 * document links were `hover:underline`: colour alone at rest. That fails
 * WCAG 1.4.1 (colour is not the only means of conveying information), it is
 * what Berman v. Freedom Financial found insufficient for putting somebody on
 * notice of terms, and on a phone there is no hover at all — so on the device
 * most of these readers use, the links to the documents they are being asked
 * to accept were styled as plain text.
 */

const ROOT = join(__dirname, "..", "..", "..")
const LEGAL_SCREENS = [
  "components/legal/UploadRightsNotice.tsx",
  "components/legal/TeacherAgreementGate.tsx",
  "components/legal/LegalNoticeBanner.tsx",
  "components/firstRun/PrivacyPolicyStep.tsx",
]

describe("the consent screens are not dark patterns", () => {
  it("labels the button with what pressing it does, in every language", () => {
    const bundles = { en, ru, de, uk } as Record<string, typeof en>
    for (const [locale, bundle] of Object.entries(bundles)) {
      for (const label of [bundle.firstRun.privacy.next, bundle.legalGate.teacher.next]) {
        expect(label.length, `${locale}: the label is empty`).toBeGreaterThan(0)
        // Not a navigation word on its own. Each language's word for "accept"
        // has to be in there, because that is what the press means.
        const accepts = /accept|принять|принима|annehmen|прийняти|прийма/i.test(label)
        expect(accepts, `${locale}: "${label}" does not say the click is an acceptance`).toBe(true)
      }
    }
  })

  it("underlines every document link at rest, not only under a cursor", () => {
    for (const file of LEGAL_SCREENS) {
      const source = readFileSync(join(ROOT, file), "utf8")
      expect(
        source.includes("hover:underline"),
        `${file}: a link that is only underlined on hover is plain text on a phone`,
      ).toBe(false)
      expect(source).toContain("underline underline-offset-4")
    }
  })
})
