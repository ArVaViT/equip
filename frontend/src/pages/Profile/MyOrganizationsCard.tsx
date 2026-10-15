import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { ArrowRight, Building2 } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useAsyncData } from "@/hooks/useAsyncData"
import { organizationsService } from "@/services/organizations"

/**
 * The organizations the reader belongs to, with the role they hold in each —
 * one person can study in one, teach in another and direct a third.
 * Absent for somebody who belongs nowhere.
 */
export function MyOrganizationsCard({ userId }: { userId: string }) {
  const { t } = useTranslation()
  const { data } = useAsyncData(() => organizationsService.mine().catch(() => []), [userId])
  if (!data || data.length === 0) return null
  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle>{t("myOrganizations.title")}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {data.map((block) => (
            <li key={block.organization_id}>
              <Link
                to={`/o/${block.organization_slug}`}
                className="lift group flex items-center gap-3 rounded-lg bg-muted/15 p-4 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                  <Building2 className="h-5 w-5 text-ink-muted" strokeWidth={1.75} aria-hidden />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{block.organization_name}</p>
                  <p className="text-xs text-ink-muted first-letter:uppercase">{t(`myOrganizations.roles.${block.role}`)}</p>
                </div>
                <ArrowRight
                  className="h-4 w-4 shrink-0 text-ink-muted transition-transform duration-base group-hover:translate-x-0.5 group-hover:text-ink"
                  strokeWidth={1.75}
                  aria-hidden
                />
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
