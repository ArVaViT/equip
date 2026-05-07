import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/native-select"
import { Button } from "@/components/ui/button"
import { Users, Search, Trash2 } from "lucide-react"
import { toProxyImage } from "@/lib/images"
import PageSpinner from "@/components/ui/PageSpinner"
import VirtualAdminUsers from "../VirtualAdminUsers"
import type { UserRole } from "@/types"
import { formatDate } from "@/i18n/format"
import {
  type ProfileRow,
  ROLE_BADGE_CLASS,
  ROLE_DISPLAY_NAMES,
} from "./constants"

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
  const allFilteredSelected =
    filtered.length > 0 && filtered.every((u) => selectedIds.has(u.id))

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-4 space-y-0 flex-wrap">
        <CardTitle className="text-xl">Users</CardTitle>
        <div className="flex items-center gap-3 flex-wrap">
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-2 bg-primary/5 border border-primary/20 rounded-lg px-3 py-1.5">
              <span className="text-xs font-medium">{selectedIds.size} selected</span>
              <NativeSelect
                fieldSize="xs"
                value={bulkRole}
                onChange={(e) => onBulkRoleChange(e.target.value as UserRole)}
              >
                <option value="student">Student</option>
                <option value="pending_teacher">Pending Teacher</option>
                <option value="teacher">Teacher</option>
                <option value="admin">Admin</option>
              </NativeSelect>
              <Button
                size="sm"
                className="h-7 text-xs"
                onClick={onApplyBulkRole}
                disabled={bulkUpdating}
              >
                {bulkUpdating ? "Updating..." : "Apply"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={onClearSelection}
              >
                Clear
              </Button>
            </div>
          )}
          <div className="relative w-full max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" strokeWidth={1.75} aria-hidden="true" />
            <Input
              placeholder="Search by name or email…"
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
                aria-label="Select all users"
              />
              <span className="text-xs text-muted-foreground">
                Select all {filtered.length}
              </span>
            </div>
            <VirtualAdminUsers
              users={filtered}
              selectedIds={selectedIds}
              updatingId={updatingId}
              currentUserId={currentUserId}
              roleBadgeClass={ROLE_BADGE_CLASS}
              roleDisplayNames={ROLE_DISPLAY_NAMES}
              onToggleSelect={onToggleSelect}
              onRoleChange={onRoleChange}
              onDeleteUser={onDeleteUser}
            />
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
            Showing {filtered.length} of {users.length} users
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function EmptyUsers({ hasQuery }: { hasQuery: boolean }) {
  return (
    <div className="flex flex-col items-center py-16 text-center">
      <Users className="h-12 w-12 text-muted-foreground/40 mb-3" />
      <p className="text-muted-foreground">
        {hasQuery ? "No users match your search" : "No users found"}
      </p>
    </div>
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
  const allFilteredSelected =
    filtered.length > 0 && filtered.every((u) => selectedIds.has(u.id))

  return (
    <div className="overflow-x-auto -mx-6">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="px-3 py-3 w-10">
              <input
                type="checkbox"
                checked={allFilteredSelected}
                onChange={onToggleSelectAll}
                className="h-4 w-4 rounded border-input"
                aria-label="Select all users"
              />
            </th>
            <th className="px-6 py-3 font-medium text-muted-foreground">Name</th>
            <th className="px-6 py-3 font-medium text-muted-foreground">Email</th>
            <th className="px-6 py-3 font-medium text-muted-foreground">Role</th>
            <th className="px-6 py-3 font-medium text-muted-foreground">Joined</th>
            <th className="px-6 py-3 w-10" aria-label="Actions" />
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
          aria-label={`Select ${user.full_name || user.email}`}
        />
      </td>
      <td className="px-6 py-3">
        <div className="flex items-center gap-3">
          {user.avatar_url ? (
            <img
              src={toProxyImage(user.avatar_url)}
              alt={`${user.full_name ?? user.email} avatar`}
              className="h-8 w-8 rounded-full object-cover"
            />
          ) : (
            <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium text-muted-foreground">
              {(user.full_name?.[0] ?? user.email[0] ?? "?").toUpperCase()}
            </div>
          )}
          <span className="font-medium">{user.full_name || "—"}</span>
        </div>
      </td>
      <td className="px-6 py-3 text-muted-foreground">{user.email}</td>
      <td className="px-6 py-3">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block px-2 py-0.5 text-xs font-medium rounded-full ${ROLE_BADGE_CLASS[user.role]}`}
          >
            {ROLE_DISPLAY_NAMES[user.role]}
          </span>
          <NativeSelect
            fieldSize="sm"
            value={user.role}
            disabled={updating || isSelf}
            onChange={(e) => onRoleChange(user.id, e.target.value as UserRole)}
          >
            <option value="student">Student</option>
            <option value="pending_teacher">Pending Teacher</option>
            <option value="teacher">Teacher</option>
            <option value="admin">Admin</option>
          </NativeSelect>
        </div>
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
          aria-label={`Delete ${user.full_name || user.email}`}
          title={isSelf ? "You cannot delete your own account" : "Delete user"}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </td>
    </tr>
  )
}
