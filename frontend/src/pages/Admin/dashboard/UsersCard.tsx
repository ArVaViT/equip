import { lazy, Suspense } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/native-select"
import { Button } from "@/components/ui/button"
import { Users, Search, Trash2 } from "lucide-react"
import { toProxyImage } from "@/lib/images"
import PageSpinner from "@/components/ui/PageSpinner"
import { EmptyState } from "@/components/patterns/EmptyState"
import { RoleSelector } from "@/components/admin/RoleSelector"
import type { UserRole } from "@/types"
import { formatDate } from "@/i18n/format"
import { type ProfileRow } from "./constants"

// Only rendered when the filtered list crosses USERS_VIRTUAL_THRESHOLD —
// keeps `react-window` (~10 KB gz) out of the eager AdminDashboard chunk
// for the common case (small tenants with <50 users).
const VirtualAdminUsers = lazy(() => import("../VirtualAdminUsers"))

/**
 * Above this row count we swap the full <table> render for a react-window
 * list. Small tenants keep the familiar semantic table; large tenants
 * avoid paying ~500 avatar images + <select>s worth of DOM on mount.
 */
const USERS_VIRTUAL_THRESHOLD = 50

interface Props {
  users: ProfileRow[]
  filtered: ProfileRow[]
  loading: boolean
  searchInput: string
  searchMaxLength: number
  urlQuery: string
  selectedIds: Set<string>
  bulkRole: UserRole
  bulkUpdating: boolean
  updatingId: string | null
  currentUserId: string | undefined
  onSearchInputChange: (next: string) => void
  onBulkRoleChange: (next: UserRole) => void
  onApplyBulkRole: () => void
  onClearSelection: () => void
  onToggleSelectAll: () => void
  onToggleSelect: (id: string) => void
  onRoleChange: (userId: string, role: UserRole) => void
  onDeleteUser: (user: ProfileRow) => void
}

/** Main users table + bulk-action bar + search input. */
export function UsersCard({
  users,
  filtered,
  loading,
  searchInput,
  searchMaxLength,
  urlQuery,
  selectedIds,
  bulkRole,
  bulkUpdating,
  updatingId,
  currentUserId,
  onSearchInputChange,
  onBulkRoleChange,
  onApplyBulkRole,
  onClearSelection,
  onToggleSelectAll,
  onToggleSelect,
  onRoleChange,
  onDeleteUser,
}: Props) {
  const { t } = useTranslation()
  const allFilteredSelected =
    filtered.length > 0 && filtered.every((u) => selectedIds.has(u.id))

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-4 space-y-0 flex-wrap">
        <CardTitle className="text-xl">{t("admin.users.title")}</CardTitle>
        <div className="flex items-center gap-3 flex-wrap">
          {selectedIds.size > 0 && (
            <div className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-1.5 sm:w-auto">
              <span className="text-xs font-medium">{t("admin.users.selected", { count: selectedIds.size })}</span>
              <NativeSelect
                fieldSize="sm"
                value={bulkRole}
                onChange={(e) => onBulkRoleChange(e.target.value as UserRole)}
                className="w-auto"
              >
                <option value="student">{t("roles.student")}</option>
                <option value="pending_teacher">{t("roles.pendingTeacher")}</option>
                <option value="teacher">{t("roles.teacher")}</option>
                <option value="admin">{t("roles.admin")}</option>
              </NativeSelect>
              <Button
                size="sm"
                className="h-9 text-xs sm:h-7"
                onClick={onApplyBulkRole}
                disabled={bulkUpdating}
              >
                {bulkUpdating ? t("admin.users.bulkUpdating") : t("admin.users.bulkApply")}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-9 text-xs sm:h-7"
                onClick={onClearSelection}
              >
                {t("admin.users.bulkClear")}
              </Button>
            </div>
          )}
          <div className="relative w-full max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" strokeWidth={1.75} aria-hidden="true" />
            <Input
              placeholder={t("admin.users.searchPlaceholder")}
              value={searchInput}
              onChange={(e) => onSearchInputChange(e.target.value.slice(0, searchMaxLength))}
              maxLength={searchMaxLength}
              className="pl-9"
            />
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <PageSpinner />
        ) : filtered.length === 0 ? (
          <EmptyUsers hasQuery={Boolean(urlQuery)} />
        ) : filtered.length >= USERS_VIRTUAL_THRESHOLD ? (
          <>
            <div className="flex items-center gap-3 px-3 pb-2">
              <input
                type="checkbox"
                checked={allFilteredSelected}
                onChange={onToggleSelectAll}
                className="h-4 w-4 rounded border-input"
                aria-label={t("admin.users.selectAllAria")}
              />
              <span className="text-xs text-muted-foreground">
                {t("admin.users.selectAllN", { count: filtered.length })}
              </span>
            </div>
            <Suspense fallback={<PageSpinner />}>
              <VirtualAdminUsers
                users={filtered}
                selectedIds={selectedIds}
                updatingId={updatingId}
                currentUserId={currentUserId}
                onToggleSelect={onToggleSelect}
                onRoleChange={onRoleChange}
                onDeleteUser={onDeleteUser}
              />
            </Suspense>
          </>
        ) : (
          <UsersTable
            filtered={filtered}
            selectedIds={selectedIds}
            updatingId={updatingId}
            currentUserId={currentUserId}
            onToggleSelectAll={onToggleSelectAll}
            onToggleSelect={onToggleSelect}
            onRoleChange={onRoleChange}
            onDeleteUser={onDeleteUser}
          />
        )}
        {!loading && filtered.length > 0 && (
          <p className="text-xs text-muted-foreground mt-4 px-6">
            {t("admin.users.showing", { shown: filtered.length, total: users.length })}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function EmptyUsers({ hasQuery }: { hasQuery: boolean }) {
  const { t } = useTranslation()
  return (
    <EmptyState
      variant="compact"
      icon={<Users strokeWidth={1.75} aria-hidden />}
      title={
        hasQuery ? t("admin.users.emptyNoMatch") : t("admin.users.emptyNoUsers")
      }
    />
  )
}

interface UsersTableProps {
  filtered: ProfileRow[]
  selectedIds: Set<string>
  updatingId: string | null
  currentUserId: string | undefined
  onToggleSelectAll: () => void
  onToggleSelect: (id: string) => void
  onRoleChange: (userId: string, role: UserRole) => void
  onDeleteUser: (user: ProfileRow) => void
}

function UsersTable({
  filtered,
  selectedIds,
  updatingId,
  currentUserId,
  onToggleSelectAll,
  onToggleSelect,
  onRoleChange,
  onDeleteUser,
}: UsersTableProps) {
  const { t } = useTranslation()
  const allFilteredSelected =
    filtered.length > 0 && filtered.every((u) => selectedIds.has(u.id))

  return (
    <>
      {/* Mobile: stacked card list — the table doesn't fit a phone. Same
          data, same controls, larger tap targets. */}
      <div className="-mx-3 space-y-2 sm:hidden">
        <label className="mx-3 flex min-h-[44px] items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={allFilteredSelected}
            onChange={onToggleSelectAll}
            className="h-4 w-4 rounded border-input"
            aria-label={t("admin.users.selectAllAria")}
          />
          <span>{t("admin.users.selectAllN", { count: filtered.length })}</span>
        </label>
        <div className="mx-3 space-y-2">
          {filtered.map((u) => (
            <UserCard
              key={u.id}
              user={u}
              selected={selectedIds.has(u.id)}
              updating={updatingId === u.id}
              isSelf={u.id === currentUserId}
              onToggleSelect={onToggleSelect}
              onRoleChange={onRoleChange}
              onDeleteUser={onDeleteUser}
            />
          ))}
        </div>
      </div>

      {/* Desktop: classic semantic table with internal scroll + sticky
          header. ``max-h-[60vh]`` matches the audit log so the users
          panel doesn't push the admin overview off-screen when the
          tenant grows past 20-30 rows. */}
      <div className="-mx-6 hidden max-h-[60vh] overflow-y-auto sm:block">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-card">
            <tr className="border-b text-left">
              <th className="w-10 px-3 py-3">
                <input
                  type="checkbox"
                  checked={allFilteredSelected}
                  onChange={onToggleSelectAll}
                  className="h-4 w-4 rounded border-input"
                  aria-label={t("admin.users.selectAllAria")}
                />
              </th>
              <th className="px-6 py-3 font-medium text-muted-foreground">{t("admin.users.thName")}</th>
              <th className="px-6 py-3 font-medium text-muted-foreground">{t("admin.users.thEmail")}</th>
              <th className="px-6 py-3 font-medium text-muted-foreground">{t("admin.users.thRole")}</th>
              <th className="px-6 py-3 font-medium text-muted-foreground">{t("admin.users.thJoined")}</th>
              <th className="w-10 px-6 py-3" aria-label={t("admin.users.thActions")} />
            </tr>
          </thead>
          <tbody className="divide-y">
            {filtered.map((u) => (
              <UserRow
                key={u.id}
                user={u}
                selected={selectedIds.has(u.id)}
                updating={updatingId === u.id}
                isSelf={u.id === currentUserId}
                onToggleSelect={onToggleSelect}
                onRoleChange={onRoleChange}
                onDeleteUser={onDeleteUser}
              />
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function UserCard({
  user,
  selected,
  updating,
  isSelf,
  onToggleSelect,
  onRoleChange,
  onDeleteUser,
}: UserRowProps) {
  const { t } = useTranslation()
  const displayName = user.full_name || user.email
  return (
    <div
      className={`rounded-md border border-border bg-card p-3 transition-colors ${
        selected ? "border-primary/40 bg-primary/[0.03]" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggleSelect(user.id)}
          className="mt-1.5 h-4 w-4 shrink-0 rounded border-input"
          aria-label={t("admin.users.selectAriaPrefix", { name: displayName })}
        />
        {user.avatar_url ? (
          <img
            src={toProxyImage(user.avatar_url)}
            alt={t("admin.users.avatarAltPrefix", { name: user.full_name ?? user.email })}
            className="h-10 w-10 shrink-0 rounded-full object-cover"
          />
        ) : (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-medium text-muted-foreground">
            {(user.full_name?.[0] ?? user.email[0] ?? "?").toUpperCase()}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">
            {user.full_name || t("admin.users.missingName")}
          </p>
          <p className="truncate text-xs text-muted-foreground">{user.email}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {formatDate(user.created_at)}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="h-11 w-11 shrink-0 p-0 text-muted-foreground hover:text-destructive"
          disabled={updating || isSelf}
          onClick={() => onDeleteUser(user)}
          aria-label={t("admin.users.deleteAriaPrefix", { name: displayName })}
          title={isSelf ? t("admin.users.deleteSelfTooltip") : t("admin.users.deleteTooltip")}
        >
          <Trash2 className="h-4 w-4" strokeWidth={1.75} />
        </Button>
      </div>
      <div className="mt-3 pl-7">
        <RoleSelector
          role={user.role}
          disabled={updating || isSelf}
          onChange={(next) => onRoleChange(user.id, next)}
          ariaLabel={t("admin.users.changeRoleAria", { name: displayName })}
        />
      </div>
    </div>
  )
}

interface UserRowProps {
  user: ProfileRow
  selected: boolean
  updating: boolean
  isSelf: boolean
  onToggleSelect: (id: string) => void
  onRoleChange: (userId: string, role: UserRole) => void
  onDeleteUser: (user: ProfileRow) => void
}

function UserRow({
  user,
  selected,
  updating,
  isSelf,
  onToggleSelect,
  onRoleChange,
  onDeleteUser,
}: UserRowProps) {
  const { t } = useTranslation()
  const displayName = user.full_name || user.email
  return (
    <tr
      className={`hover:bg-muted/50 transition-colors ${
        selected ? "bg-primary/[0.03]" : ""
      }`}
    >
      <td className="px-3 py-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggleSelect(user.id)}
          className="h-4 w-4 rounded border-input"
          aria-label={t("admin.users.selectAriaPrefix", { name: displayName })}
        />
      </td>
      <td className="px-6 py-3">
        <div className="flex items-center gap-3">
          {user.avatar_url ? (
            <img
              src={toProxyImage(user.avatar_url)}
              alt={t("admin.users.avatarAltPrefix", { name: user.full_name ?? user.email })}
              className="h-8 w-8 rounded-full object-cover"
            />
          ) : (
            <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium text-muted-foreground">
              {(user.full_name?.[0] ?? user.email[0] ?? "?").toUpperCase()}
            </div>
          )}
          <span className="font-medium">{user.full_name || t("admin.users.missingName")}</span>
        </div>
      </td>
      <td className="px-6 py-3 text-muted-foreground">{user.email}</td>
      <td className="px-6 py-3">
        <RoleSelector
          role={user.role}
          disabled={updating || isSelf}
          onChange={(next) => onRoleChange(user.id, next)}
          ariaLabel={t("admin.users.changeRoleAria", { name: displayName })}
        />
      </td>
      <td className="px-6 py-3 text-muted-foreground">
        {formatDate(user.created_at)}
      </td>
      <td className="px-3 py-3">
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
          disabled={updating || isSelf}
          onClick={() => onDeleteUser(user)}
          aria-label={t("admin.users.deleteAriaPrefix", { name: displayName })}
          title={isSelf ? t("admin.users.deleteSelfTooltip") : t("admin.users.deleteTooltip")}
        >
          <Trash2 className="h-4 w-4" strokeWidth={1.75} />
        </Button>
      </td>
    </tr>
  )
}
