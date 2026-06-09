import { lazy, Suspense } from "react"
import { useTranslation } from "react-i18next"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { Users, Search, Trash2, RotateCcw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import PageSpinner from "@/components/ui/PageSpinner"
import { EmptyState } from "@/components/patterns/EmptyState"
import { RoleSelector } from "@/components/admin/RoleSelector"
import { UserAvatar } from "@/components/admin/UserAvatar"
import { displayNameOf } from "@/lib/userDisplay"
import { ROLE_I18N_KEY } from "@/lib/roles"
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

/** Empty string = "all roles" (no filter). */
export type RoleFilterValue = "" | "admin" | "teacher" | "student"

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
  roleFilter: RoleFilterValue
  roleCounts: Record<UserRole, number>
  onRoleFilterChange: (next: RoleFilterValue) => void
  onSearchInputChange: (next: string) => void
  onBulkRoleChange: (next: UserRole) => void
  onApplyBulkRole: () => void
  onClearSelection: () => void
  onToggleSelectAll: () => void
  onToggleSelect: (id: string) => void
  onRoleChange: (userId: string, role: UserRole) => void
  onDeleteUser: (user: ProfileRow) => void
  onRestoreUser: (user: ProfileRow) => void
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
  roleFilter,
  roleCounts,
  onRoleFilterChange,
  onSearchInputChange,
  onBulkRoleChange,
  onApplyBulkRole,
  onClearSelection,
  onToggleSelectAll,
  onToggleSelect,
  onRoleChange,
  onDeleteUser,
  onRestoreUser,
}: Props) {
  const { t } = useTranslation()
  const allFilteredSelected =
    filtered.length > 0 && filtered.every((u) => selectedIds.has(u.id))
  // Three-state select-all: ``true`` when every row in the current
  // filtered view is selected, ``"indeterminate"`` when only some are
  // (Checkbox renders the dash glyph), ``false`` when none.
  const selectAllState: boolean | "indeterminate" = allFilteredSelected
    ? true
    : selectedIds.size > 0
      ? "indeterminate"
      : false

  return (
    <Card>
      <CardHeader className="space-y-4">
        {/* Row 1: title only. Keeps the visual hierarchy honest --
            previously the title competed with three controls in a
            single flex-wrap row, and at laptop widths the chip strip
            below would wrap up under the search input creating an
            orphan visual that looked unfinished. */}
        <CardTitle className="font-serif text-lg font-semibold tracking-tight">{t("admin.users.title")}</CardTitle>

        {/* Row 2: filter + search aligned right. ``items-center`` so
            the search h-9 input and select line up; ``ml-auto`` pushes
            the controls to the trailing edge on wide widths but stays
            stackable on mobile via ``flex-wrap``. */}
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={roleFilter || "all"}
            onValueChange={(v) =>
              onRoleFilterChange((v === "all" ? "" : v) as RoleFilterValue)
            }
          >
            <SelectTrigger
              size="sm"
              aria-label={t("admin.users.roleFilterAria")}
              className={cn(
                "h-9 w-full sm:w-44",
                roleFilter && "border-brand/40 ring-1 ring-primary/40",
              )}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("admin.users.roleFilterAll")}</SelectItem>
              <SelectItem value="admin">{t("roles.admin")}</SelectItem>
              <SelectItem value="teacher">{t("roles.teacher")}</SelectItem>
              <SelectItem value="student">{t("roles.student")}</SelectItem>
            </SelectContent>
          </Select>
          <div className="relative w-full sm:max-w-xs sm:flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted"
              strokeWidth={1.75}
              aria-hidden
            />
            <Input
              placeholder={t("admin.users.searchPlaceholder")}
              value={searchInput}
              onChange={(e) => onSearchInputChange(e.target.value.slice(0, searchMaxLength))}
              maxLength={searchMaxLength}
              className="pl-9"
            />
          </div>
        </div>

        {/* Row 3: role distribution chip strip — clickable shortcuts
            for the filter that double as a tenant-shape snapshot.
            Hides zero-count roles so the strip stays meaningful on
            small tenants. Active filter gets the primary fill. */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {(["admin", "teacher", "student"] as const).map((role) => {
            if (roleCounts[role] === 0) return null
            const active = roleFilter === role
            return (
              <button
                key={role}
                type="button"
                onClick={() => onRoleFilterChange(active ? "" : role)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 transition-colors",
                  active
                    ? "border-brand bg-brand text-brand-foreground"
                    : "border-edge hover:border-brand/40 hover:bg-muted",
                )}
              >
                <span>{t(ROLE_I18N_KEY[role])}</span>
                <span
                  className={cn(
                    "tabular-nums",
                    active ? "opacity-90" : "text-ink-muted",
                  )}
                >
                  {roleCounts[role]}
                </span>
              </button>
            )
          })}
        </div>

        {/* Row 4 (conditional): bulk-action bar. Lives below the
            distribution strip rather than competing with title +
            filters above; appears only when at least one row is
            selected. Full-width tinted card makes the "selection
            mode" state obvious. */}
        {selectedIds.size > 0 && (
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-brand/30 bg-brand/5 px-3 py-2">
            <span className="text-xs font-medium">
              {t("admin.users.selected", { count: selectedIds.size })}
            </span>
            <Select value={bulkRole} onValueChange={(v) => onBulkRoleChange(v as UserRole)}>
              <SelectTrigger size="sm" className="w-auto">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="student">{t("roles.student")}</SelectItem>
                <SelectItem value="teacher">{t("roles.teacher")}</SelectItem>
                <SelectItem value="admin">{t("roles.admin")}</SelectItem>
              </SelectContent>
            </Select>
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
      </CardHeader>
      <CardContent>
        {loading ? (
          <PageSpinner />
        ) : filtered.length === 0 ? (
          <EmptyUsers hasQuery={Boolean(urlQuery)} />
        ) : filtered.length >= USERS_VIRTUAL_THRESHOLD ? (
          <>
            <div className="flex items-center gap-3 px-3 pb-2">
              <Checkbox
                checked={selectAllState}
                onCheckedChange={onToggleSelectAll}
                aria-label={t("admin.users.selectAllAria")}
              />
              <span className="text-xs text-ink-muted">
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
                onRestoreUser={onRestoreUser}
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
            onRestoreUser={onRestoreUser}
          />
        )}
        {!loading && filtered.length > 0 && (
          <p className="mt-4 text-xs text-ink-muted">
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
  onRestoreUser: (user: ProfileRow) => void
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
  onRestoreUser,
}: UsersTableProps) {
  const { t } = useTranslation()
  const allFilteredSelected =
    filtered.length > 0 && filtered.every((u) => selectedIds.has(u.id))
  const selectAllState: boolean | "indeterminate" = allFilteredSelected
    ? true
    : selectedIds.size > 0
      ? "indeterminate"
      : false

  return (
    <>
      {/* Mobile: stacked card list — the table doesn't fit a phone. Same
          data, same controls, larger tap targets. No negative margins
          here -- the previous ``-mx-3``/``mx-3`` pair on the outer and
          inner divs cancelled out (net 0) and just made the layout
          harder to read. */}
      <div className="space-y-2 sm:hidden">
        <label className="flex min-h-[44px] items-center gap-2 text-xs text-ink-muted">
          <Checkbox
            checked={selectAllState}
            onCheckedChange={onToggleSelectAll}
            aria-label={t("admin.users.selectAllAria")}
          />
          <span>{t("admin.users.selectAllN", { count: filtered.length })}</span>
        </label>
        <div className="space-y-2">
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
              onRestoreUser={onRestoreUser}
            />
          ))}
        </div>
      </div>

      {/* Desktop: classic semantic table with internal scroll + sticky
          header. ``table-fixed`` so column widths come from <colgroup>
          rather than from cell content — a single 60-char student email
          can't push the actions column off-screen. ``max-h-[60vh]``
          matches the audit log so the users panel doesn't push the
          admin overview off-screen when the tenant grows past 20-30
          rows.

          ``-mx-5`` MUST match ``CardContent``'s ``p-5`` padding token
          exactly. The previous ``-mx-6`` (-24 px) against ``p-5``
          (20 px) left the table jutting 4 px past the Card's
          rounded border on each side -- the thead ``border-b`` and
          tbody ``divide-y`` rules then visibly bled out under the
          rounded corners as little stripes on the left + right
          edges. This is the cleanest fix: zero math, zero risk of
          drift if the Card token changes. */}
      <div className="-mx-5 hidden max-h-[60vh] overflow-y-auto sm:block">
        <table className="w-full table-fixed text-sm">
          <colgroup>
            <col className="w-10" />
            {/* Name: enough room for "Vadym Arnaut" + avatar without
                truncating, but capped so the rest of the row breathes. */}
            <col className="w-[26%]" />
            {/* Email: dominant column, given the most space; ellipsised
                inside a ``truncate`` cell with full text in title attr. */}
            <col className="w-[34%]" />
            {/* Role: short pill, fixed slot keeps it aligned across rows. */}
            <col className="w-[18%]" />
            {/* Joined: ISO date, tabular-nums, narrow. */}
            <col className="w-[14%]" />
            {/* Actions: single 32-px icon button. */}
            <col className="w-12" />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-card">
            <tr className="border-b text-left">
              <th className="px-3 py-3">
                <Checkbox
                  checked={selectAllState}
                  onCheckedChange={onToggleSelectAll}
                  aria-label={t("admin.users.selectAllAria")}
                />
              </th>
              <th className="px-5 py-3 font-medium text-ink-muted">{t("admin.users.thName")}</th>
              <th className="px-5 py-3 font-medium text-ink-muted">{t("admin.users.thEmail")}</th>
              <th className="px-5 py-3 font-medium text-ink-muted">{t("admin.users.thRole")}</th>
              <th className="px-5 py-3 font-medium text-ink-muted">{t("admin.users.thJoined")}</th>
              <th className="px-3 py-3" aria-label={t("admin.users.thActions")} />
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
                onRestoreUser={onRestoreUser}
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
  onRestoreUser,
}: UserRowProps) {
  const { t } = useTranslation()
  const displayName = displayNameOf(user.full_name, user.email)
  const deactivated = user.deactivated_at !== null
  return (
    <div
      className={cn(
        "rounded-md bg-card p-3 transition-colors",
        selected && "border-brand/40 bg-brand/[0.08] dark:bg-brand/15",
      )}
    >
      <div className="flex items-start gap-3">
        <Checkbox
          className="mt-1.5"
          checked={selected}
          onCheckedChange={() => onToggleSelect(user.id)}
          aria-label={t("admin.users.selectAriaPrefix", { name: displayName })}
        />
        <UserAvatar
          avatarUrl={user.avatar_url}
          fullName={user.full_name}
          email={user.email}
          size="md"
          alt={t("admin.users.avatarAltPrefix", { name: displayName })}
        />
        <div className="min-w-0 flex-1">
          <p className={cn("truncate text-sm font-medium text-ink", deactivated && "text-ink-muted line-through")}>
            {user.full_name?.trim() || t("admin.users.missingName")}
          </p>
          {deactivated && (
            <Badge variant="muted" className="mt-0.5">{t("admin.users.deactivatedBadge")}</Badge>
          )}
          <p className="truncate text-xs text-ink-muted">{user.email}</p>
          <p className="mt-1 text-xs text-ink-muted">
            {formatDate(user.created_at)}
          </p>
        </div>
        {deactivated ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-11 w-11 shrink-0 p-0 text-ink-muted hover:text-brand"
            disabled={updating}
            onClick={() => onRestoreUser(user)}
            aria-label={t("admin.users.restoreAriaPrefix", { name: displayName })}
            title={t("admin.users.restoreTooltip")}
          >
            <RotateCcw className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="h-11 w-11 shrink-0 p-0 text-ink-muted hover:text-destructive"
            disabled={updating || isSelf}
            onClick={() => onDeleteUser(user)}
            aria-label={t("admin.users.deleteAriaPrefix", { name: displayName })}
            title={isSelf ? t("admin.users.deleteSelfTooltip") : t("admin.users.deleteTooltip")}
          >
            <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
        )}
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
  onRestoreUser: (user: ProfileRow) => void
}

function UserRow({
  user,
  selected,
  updating,
  isSelf,
  onToggleSelect,
  onRoleChange,
  onDeleteUser,
  onRestoreUser,
}: UserRowProps) {
  const { t } = useTranslation()
  const displayName = displayNameOf(user.full_name, user.email)
  const deactivated = user.deactivated_at !== null
  return (
    <tr
      className={cn(
        "transition-colors hover:bg-muted/40",
        selected && "bg-brand/[0.08] dark:bg-brand/15",
      )}
    >
      <td className="px-3 py-3">
        <Checkbox
          checked={selected}
          onCheckedChange={() => onToggleSelect(user.id)}
          aria-label={t("admin.users.selectAriaPrefix", { name: displayName })}
        />
      </td>
      <td className="px-5 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <UserAvatar
            avatarUrl={user.avatar_url}
            fullName={user.full_name}
            email={user.email}
            size="sm"
            alt={t("admin.users.avatarAltPrefix", { name: displayName })}
          />
          <span
            className={cn("min-w-0 truncate font-medium", deactivated && "text-ink-muted line-through")}
            title={user.full_name ?? undefined}
          >
            {user.full_name?.trim() || t("admin.users.missingName")}
          </span>
          {deactivated && (
            <Badge variant="muted" className="shrink-0">{t("admin.users.deactivatedBadge")}</Badge>
          )}
        </div>
      </td>
      <td className="px-5 py-3 text-ink-muted">
        <span className="block truncate" title={user.email}>{user.email}</span>
      </td>
      <td className="px-5 py-3">
        <RoleSelector
          role={user.role}
          disabled={updating || isSelf}
          onChange={(next) => onRoleChange(user.id, next)}
          ariaLabel={t("admin.users.changeRoleAria", { name: displayName })}
        />
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-xs text-ink-muted tabular-nums">
        {formatDate(user.created_at)}
      </td>
      <td className="px-3 py-3 text-right">
        {deactivated ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 text-ink-muted hover:text-brand"
            disabled={updating}
            onClick={() => onRestoreUser(user)}
            aria-label={t("admin.users.restoreAriaPrefix", { name: displayName })}
            title={t("admin.users.restoreTooltip")}
          >
            <RotateCcw className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 text-ink-muted hover:text-destructive"
            disabled={updating || isSelf}
            onClick={() => onDeleteUser(user)}
            aria-label={t("admin.users.deleteAriaPrefix", { name: displayName })}
            title={isSelf ? t("admin.users.deleteSelfTooltip") : t("admin.users.deleteTooltip")}
          >
            <Trash2 className="h-4 w-4" strokeWidth={1.75} aria-hidden />
          </Button>
        )}
      </td>
    </tr>
  )
}
