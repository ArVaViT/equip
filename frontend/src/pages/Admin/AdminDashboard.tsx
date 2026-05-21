import { lazy, Suspense } from "react"
import { Navigate, useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Shield } from "lucide-react"
import { useAuth } from "@/context/useAuth"
import { Button } from "@/components/ui/button"
import { ErrorState } from "@/components/patterns"
import PageSpinner from "@/components/ui/PageSpinner"
import { ADMIN_TABS, type AdminTab } from "./dashboard/constants"
import { AdminTabs } from "./dashboard/AdminTabs"
import { OverviewStats } from "./dashboard/OverviewStats"
import { PendingTeachersCard } from "./dashboard/PendingTeachersCard"
import { PendingCertsCard } from "./dashboard/PendingCertsCard"
import { UsersCard } from "./dashboard/UsersCard"
import { useAdminOverview } from "./dashboard/useAdminOverview"
import { useAdminAudit } from "./dashboard/useAdminAudit"

// The audit log and cohorts tabs are rarely the entry point — most admins
// land on Overview. Splitting them off keeps the initial AdminDashboard
// chunk lean (no react-window for cohorts via VirtualAdminUsers is still in
// UsersCard, but the audit table machinery and the cohorts list components
// don't need to ship until the matching tab is selected).
const AuditLogTab = lazy(() =>
  import("./dashboard/AuditLogTab").then((m) => ({ default: m.AuditLogTab })),
)
const CohortsTab = lazy(() =>
  import("./cohorts/CohortsTab").then((m) => ({ default: m.CohortsTab })),
)

/**
 * Admin dashboard orchestrator. Delegates every piece of state to
 * tab-scoped hooks (`useAdminOverview`, `useAdminAudit`) and renders
 * the matching section for the active tab. This file is layout-only.
 */
export default function AdminDashboard() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()

  const rawTab = params.get("tab")
  const tab: AdminTab = ADMIN_TABS.includes(rawTab as AdminTab)
    ? (rawTab as AdminTab)
    : "overview"

  // Overview data is needed by the overview tab itself AND by the audit
  // tab (audit rows show the user's name via ``userMap``, which is
  // derived from the same users list). The cohorts tab needs neither,
  // so we skip the whole overview fetch when the user opens that tab
  // directly via ``?tab=cohorts``. Saves four service round-trips
  // (users, courses count, enrollments count, pending certs) on every
  // cold visit to the cohorts surface.
  const overviewEnabled = tab === "overview" || tab === "audit"
  const overview = useAdminOverview({ currentUserId: user?.id, enabled: overviewEnabled })
  const audit = useAdminAudit({ enabled: tab === "audit" })

  if (user?.role !== "admin") return <Navigate to="/" replace />

  const setTab = (nextTab: AdminTab) => {
    const next = new URLSearchParams(params)
    if (nextTab === "overview") next.delete("tab")
    else next.set("tab", nextTab)
    setParams(next, { replace: true })
  }

  return (
    <div className="animate-fade-in container mx-auto max-w-6xl px-4 py-6 sm:py-8">
      <header className="mb-6 space-y-2">
        <p className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
          {t("admin.eyebrow")}
        </p>
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-primary/10 p-2">
            <Shield className="h-6 w-6 text-primary" strokeWidth={1.75} />
          </div>
          <h1 className="font-serif text-2xl font-bold tracking-tight sm:text-3xl">
            {t("admin.title")}
          </h1>
        </div>
      </header>

      <AdminTabs active={tab} onChange={setTab} />

      {overview.error && (
        <ErrorState
          icon={<Shield strokeWidth={1.75} />}
          description={overview.error}
          action={
            <Button onClick={overview.reload} size="sm" variant="outline">
              {t("common.tryAgain")}
            </Button>
          }
          className="mb-8"
        />
      )}

      {!overview.error && tab === "overview" && (
        <>
          <OverviewStats
            stats={overview.stats}
            loading={overview.loading}
            pendingActions={overview.pendingTeachers.length + overview.adminCerts.length}
          />
          <PendingTeachersCard
            pending={overview.pendingTeachers}
            updatingId={overview.updatingId}
            onApprove={overview.approvePendingTeacher}
            onDeny={overview.denyPendingTeacher}
          />
          <PendingCertsCard
            certs={overview.adminCerts}
            actionId={overview.certActionId}
            onApprove={overview.handleFinalApproveCert}
            onReject={overview.handleRejectCert}
          />
          <UsersCard
            users={overview.users}
            filtered={overview.filtered}
            loading={overview.loading}
            searchInput={overview.searchInput}
            searchMaxLength={overview.searchMaxLength}
            urlQuery={overview.urlQuery}
            selectedIds={overview.selectedIds}
            bulkRole={overview.bulkRole}
            bulkUpdating={overview.bulkUpdating}
            updatingId={overview.updatingId}
            currentUserId={user?.id}
            roleFilter={overview.roleFilter}
            roleCounts={overview.roleCounts}
            onRoleFilterChange={overview.setRoleFilter}
            onSearchInputChange={overview.setSearchInput}
            onBulkRoleChange={overview.setBulkRole}
            onApplyBulkRole={overview.handleBulkRoleChange}
            onClearSelection={overview.clearSelection}
            onToggleSelectAll={overview.toggleSelectAll}
            onToggleSelect={overview.toggleSelect}
            onRoleChange={overview.handleRoleChange}
            onDeleteUser={overview.handleDeleteUser}
          />
        </>
      )}

      {tab === "cohorts" && (
        <Suspense fallback={<PageSpinner />}>
          <CohortsTab />
        </Suspense>
      )}

      {!overview.error && tab === "audit" && (
        <Suspense fallback={<PageSpinner />}>
          <AuditLogTab
            logs={audit.logs}
            total={audit.total}
            loading={audit.loading}
            page={audit.page}
            pageSize={audit.pageSize}
            userMap={overview.userMap}
            action={audit.action}
            resource={audit.resource}
            dateFrom={audit.dateFrom}
            dateTo={audit.dateTo}
            onAction={audit.setAction}
            onResource={audit.setResource}
            onDateRange={audit.setDateRange}
            onReset={audit.resetFilters}
            onPageChange={audit.setPage}
            onPageSizeChange={audit.setPageSize}
          />
        </Suspense>
      )}
    </div>
  )
}
