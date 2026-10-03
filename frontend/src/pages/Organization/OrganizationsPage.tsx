import { useTranslation } from "react-i18next"
import { Building2 } from "lucide-react"

import { OrganizationCards } from "@/components/organization/OrganizationCards"
import { EmptyState, ErrorState, Eyebrow } from "@/components/patterns"
import PageSpinner from "@/components/ui/PageSpinner"
import { useAsyncData } from "@/hooks/useAsyncData"
import { SUPPORT_EMAIL } from "@/lib/brand"
import { organizationsService } from "@/services/organizations"

/**
 * "Organizations on Equip": the schools, churches and missions teaching
 * here — and, at the bottom, how another one joins. Joining is by agreement
 * with the platform, by email; there is no form to fill in.
 */
export default function OrganizationsPage() {
  const { t } = useTranslation()
  const { data, loading, error } = useAsyncData(() => organizationsService.list(), [])

  return (
    <div className="container mx-auto max-w-5xl px-4 py-10">
      <Eyebrow>{t("organizations.eyebrow")}</Eyebrow>
      <h1 className="mt-2 font-serif text-3xl font-semibold tracking-tight sm:text-4xl">{t("organizations.title")}</h1>
      <p className="mt-3 max-w-prose text-ink-muted">{t("organizations.lead")}</p>

      <div className="mt-8">
        {loading && !data ? (
          <PageSpinner variant="section" />
        ) : error || !data ? (
          <ErrorState title={t("organization.loadError")} />
        ) : data.length === 0 ? (
          <EmptyState icon={<Building2 strokeWidth={1.75} aria-hidden />} title={t("organizations.empty")} />
        ) : (
          <OrganizationCards cards={data} />
        )}
      </div>

      <section aria-labelledby="orgs-join" className="mt-14 rounded-card border border-edge bg-muted/30 p-6">
        <h2 id="orgs-join" className="font-serif text-xl font-semibold tracking-tight">
          {t("organizations.joinTitle")}
        </h2>
        <p className="mt-2 max-w-prose text-sm text-ink-muted">{t("organizations.joinBody")}</p>
        <a
          href={`mailto:${SUPPORT_EMAIL}`}
          className="mt-3 inline-block text-sm font-medium text-ink underline underline-offset-4 hover:text-brand"
        >
          {SUPPORT_EMAIL}
        </a>
      </section>
    </div>
  )
}
