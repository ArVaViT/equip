import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"

import { OrganizationCards } from "@/components/organization/OrganizationCards"
import { organizationsService, type OrganizationCard } from "@/services/organizations"
import { TEXT_VEIL } from "./textVeil"

/** One card does not make "organizations teach here" — it looks like a placeholder. */
const SHOWN_FROM = 2

/**
 * "Organizations teach here": the landing's proof that this is not one
 * school's site. Absent until there are at least two to show.
 */
export function OrganizationsBand() {
  const { t } = useTranslation()
  const [cards, setCards] = useState<OrganizationCard[]>([])
  useEffect(() => {
    let alive = true
    organizationsService
      .list()
      .then((list) => {
        if (alive) setCards(list)
      })
      .catch(() => {
        // A marketing page says nothing about an outage.
      })
    return () => {
      alive = false
    }
  }, [])
  if (cards.length < SHOWN_FROM) return null
  return (
    <section aria-labelledby="landing-orgs-heading" className="px-5 py-16 lg:py-24">
      <div className={`mx-auto w-full max-w-5xl ${TEXT_VEIL}`}>
        <h2 id="landing-orgs-heading" className="font-serif text-3xl font-medium tracking-[-0.025em] text-ink sm:text-4xl">
          {t("organizations.landingTitle")}
        </h2>
        <div className="mt-8">
          <OrganizationCards cards={cards.slice(0, 6)} />
        </div>
        <Link to="/organizations" className="mt-6 inline-block text-sm font-medium text-ink underline underline-offset-4 hover:text-brand">
          {t("organizations.all")}
        </Link>
      </div>
    </section>
  )
}
