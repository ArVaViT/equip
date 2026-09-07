/**
 * A failed catalog fetch must not leave the app showing its own keys.
 *
 * Seen in production on 2026-08-16: the whole interface rendered
 * `header.home`, `courses.pageTitleAuthed`, `common.appName`. i18next
 * asks its backend once per language and remembers the failure; a
 * dynamic import that lost a network round trip is not a permanent
 * fact, but nothing ever asked again. The reader's only cure was a
 * reload they had no reason to think of.
 */

import { afterEach, describe, expect, it } from "vitest"

import i18n, { DEFAULT_LOCALE } from "../config"

afterEach(async () => {
  await i18n.changeLanguage(DEFAULT_LOCALE)
})

describe("the catalog is there, and stays there", () => {
  it("the active language has real text, not its own keys", () => {
    const active = i18n.resolvedLanguage || i18n.language
    expect(i18n.hasResourceBundle(active, "translation")).toBe(true)
    expect(i18n.t("common.appName")).not.toBe("common.appName")
  })

  it("a key that exists resolves in every served language", async () => {
    for (const locale of ["ru", "en", "de", "uk"]) {
      await i18n.changeLanguage(locale)
      expect(i18n.t("header.home")).not.toBe("header.home")
    }
  })

  it("reloadResources can put a missing bundle back", async () => {
    // The recovery path the app runs on `online` / tab focus. Removing
    // the bundle is exactly the state a failed import leaves behind.
    const active = i18n.resolvedLanguage || i18n.language
    i18n.removeResourceBundle(active, "translation")

    // The namespace must be named: ``reloadResources([active])`` alone
    // resolves and restores nothing, which is how the first version of
    // the recovery path shipped doing nothing at all.
    await i18n.reloadResources([active], ["translation"])

    expect(i18n.hasResourceBundle(active, "translation")).toBe(true)
    expect(i18n.t("common.appName")).not.toBe("common.appName")
  })

  it("a language i18next has already failed on is not retried by reloadResources alone", async () => {
    // The state the real failure leaves behind, which is NOT what
    // `removeResourceBundle` produces: i18next records `-1` in
    // `backendConnector.state`, and `queueLoad` checks that before it
    // honours `reload: true`. The first version of the recovery path
    // called `reloadResources` on exactly this state and made zero
    // requests — measured against the library, not assumed.
    const active = i18n.resolvedLanguage || i18n.language
    const connector = (i18n.services as { backendConnector?: { state?: Record<string, number> } })
      .backendConnector
    expect(connector?.state, "i18next no longer keeps load state here").toBeTruthy()

    i18n.removeResourceBundle(active, "translation")
    connector!.state![`${active}|translation`] = -1

    await i18n.reloadResources([active], ["translation"])
    expect(i18n.hasResourceBundle(active, "translation")).toBe(false)

    // Forgetting the failure is what makes the retry a retry.
    delete connector!.state![`${active}|translation`]
    await i18n.reloadResources([active], ["translation"])
    expect(i18n.hasResourceBundle(active, "translation")).toBe(true)
  })
})
