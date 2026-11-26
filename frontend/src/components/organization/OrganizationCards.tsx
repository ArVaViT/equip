import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { BadgeCheck } from "lucide-react"

import { OrganizationMark } from "./OrganizationMark"
import type { OrganizationCard } from "@/services/organizations"

/**
 * Organizations as a row of cards — the showcase page and the landing band.
 * Every card is an organization the platform has verified, with a director
 * and courses (the server's filter); the badge says so.
 */
export function OrganizationCards({ cards }: { cards: OrganizationCard[] }) {
  const { t } = useTranslation()
  return (
    <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {cards.map((card) => {
        return (
          <li key={card.slug}>
            <Link
              to={`/o/${card.slug}`}
              className="group flex h-full gap-4 rounded-card border border-edge bg-surface p-5 transition-colors hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              <OrganizationMark name={card.public_name} logoUrl={card.logo_url} size="md" />
              <span className="min-w-0">
                <span className="block font-serif text-lg font-semibold tracking-tight text-wrap-safe group-hover:text-brand">
                  {card.public_name}
                </span>
                <span className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-muted">
                  <BadgeCheck className="h-3.5 w-3.5 text-success-ink" strokeWidth={1.75} aria-label={t("organization.verified")} />
                  {`${card.courses} ${t("organization.stats.courses", { count: card.courses })}`}
                </span>
                {card.description && (
                  <span className="mt-2 line-clamp-3 text-sm text-ink-muted">{card.description}</span>
                )}
              </span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
