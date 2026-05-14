import { Navigate, useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Shield } from "lucide-react"
import { useAuth } from "@/context/useAuth"
import { Button } from "@/components/ui/button"
import { ErrorState } from "@/components/patterns"
import { ADMIN_TABS, type AdminTab } from "./dashboard/constants"
import { AdminTabs } from "./dashboard/AdminTabs"
import { OverviewStats } from "./dashboard/OverviewStats"
import { PendingTeachersCard } from "./dashboard/PendingTeachersCard"
import { PendingCertsCard } from "./dashboard/PendingCertsCard"
import { UsersCard } from "./dashboard/UsersCard"
import { AuditLogTab } from "./dashboard/AuditLogTab"
import { useAdminOverview } from "./dashboard/useAdminOverview"
import { useAdminAudit } from "./dashboard/useAdminAudit"
import { CohortsTab } from "./cohorts"

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

  const overview = useAdminOverview({ currentUserId: user?.id })
  const audit = useAdminAudit({ enabled: tab === "audit" })

  if (user?.role !== "admin") return <Navigate to="/" replace />

  const setTab = (nextTab: AdminTab) => {
    const next = new URLSearchParams(params)
    if (nextTab === "overview") next.delete("tab")
    else next.set("tab", nextTab)
    setParams(next, { replace: true })
  }

  return (
    <div className="animate-fade-in container mx-auto px-4 py-8 max-w-6xl">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 rounded-lg bg-primary/10">
          <Shield className="h-6 w-6 text-primary" />
        </div>
        <h1 className="text-3xl font-serif font-bold tracking-tight">{t("admin.title")}</h1>
      </div>

      <AdminTabs active={tab} onChange={setTab} />

      {overview.error && (
        <ErrorState
          icon={<Shield />}
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
          <OverviewStats stats={overview.stats} loading={overview.loading} />
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

      {tab === "cohorts" && <CohortsTab />}

      {!overview.error && tab === "audit" && (
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
          onDateFrom={audit.setDateFrom}
          onDateTo={audit.setDateTo}
          onReset={audit.resetFilters}
          onPageChange={audit.setPage}
        />
      )}
    </div>
  )
}
