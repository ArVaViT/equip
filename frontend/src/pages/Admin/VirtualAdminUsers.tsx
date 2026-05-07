import { List, type RowComponentProps } from "react-window"
import { Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NativeSelect } from "@/components/ui/native-select"
import { toProxyImage } from "@/lib/images"
import type { UserRole } from "@/types"
import { formatDate } from "@/i18n/format"

interface ProfileRow {
  id: string
  email: string
  full_name: string | null
  role: UserRole
  created_at: string
  avatar_url: string | null
}

interface VirtualAdminUsersProps {
  users: ProfileRow[]
  selectedIds: Set<string>
  updatingId: string | null
  currentUserId: string | undefined
  roleBadgeClass: Record<string, string>
  roleDisplayNames: Record<string, string>
  onToggleSelect: (id: string) => void
  onRoleChange: (userId: string, role: UserRole) => void
  onDeleteUser: (user: ProfileRow) => void
}

type RowProps = Omit<VirtualAdminUsersProps, "users"> & { users: ProfileRow[] }

const ROW_HEIGHT = 64

function UserRow({
  index,
  style,
  users,
  selectedIds,
  updatingId,
  currentUserId,
  roleBadgeClass,
  roleDisplayNames,
  onToggleSelect,
  onRoleChange,
  onDeleteUser,
}: RowComponentProps<RowProps>) {
  const u = users[index]
  if (!u) return null
  const selected = selectedIds.has(u.id)
  return (
    <div
      role="row"
      style={style}
      className={`grid grid-cols-[40px_2fr_2fr_2fr_1fr_40px] items-center border-b px-3 text-sm hover:bg-muted/50 transition-colors ${
        selected ? "bg-primary/[0.03]" : ""
      }`}
    >
      <div role="cell" className="flex items-center justify-center">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggleSelect(u.id)}
          className="h-4 w-4 rounded border-input"
          aria-label={`Select ${u.full_name || u.email}`}
        />
      </div>
      <div role="cell" className="flex items-center gap-3 px-3 min-w-0">
        {u.avatar_url ? (
          <img
            src={toProxyImage(u.avatar_url)}
            alt={`${u.full_name ?? u.email} avatar`}
            className="h-8 w-8 rounded-full object-cover shrink-0"
            loading="lazy"
          />
        ) : (
          <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium text-muted-foreground shrink-0">
            {(u.full_name?.[0] ?? u.email[0] ?? "?").toUpperCase()}
          </div>
        )}
        <span className="font-medium truncate">{u.full_name || "—"}</span>
      </div>
      <div role="cell" className="px-3 text-muted-foreground truncate">
        {u.email}
      </div>
      <div role="cell" className="px-3 flex items-center gap-2">
        <span
          className={`inline-block px-2 py-0.5 text-xs font-medium rounded-full ${roleBadgeClass[u.role] ?? ""}`}
        >
          {roleDisplayNames[u.role] ?? u.role}
        </span>
        <NativeSelect
          fieldSize="sm"
          value={u.role}
          disabled={updatingId === u.id || u.id === currentUserId}
          onChange={(e) => onRoleChange(u.id, e.target.value as UserRole)}
        >
          <option value="student">Student</option>
          <option value="pending_teacher">Pending Teacher</option>
          <option value="teacher">Teacher</option>
          <option value="admin">Admin</option>
        </NativeSelect>
      </div>
      <div role="cell" className="px-3 text-muted-foreground">
        {formatDate(u.created_at)}
      </div>
      <div role="cell" className="flex items-center justify-center">
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
          disabled={updatingId === u.id || u.id === currentUserId}
          onClick={() => onDeleteUser(u)}
          aria-label={`Delete ${u.full_name || u.email}`}
          title={u.id === currentUserId ? "You cannot delete your own account" : "Delete user"}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

export default function VirtualAdminUsers({
  users,
  selectedIds,
  updatingId,
  currentUserId,
  roleBadgeClass,
  roleDisplayNames,
  onToggleSelect,
  onRoleChange,
  onDeleteUser,
}: VirtualAdminUsersProps) {
  // Height budget: enough to show ~10 rows before the window scrolls. Keeps the
  // admin dashboard from running off the viewport on long tenant lists.
  const height = Math.min(users.length * ROW_HEIGHT, 640)

  return (
    <div role="table" aria-rowcount={users.length} className="-mx-6">
      <div
        role="row"
        className="grid grid-cols-[40px_2fr_2fr_2fr_1fr_40px] items-center border-b px-3 py-3 text-xs font-medium text-muted-foreground"
      >
        <div role="columnheader" />
        <div role="columnheader" className="px-3">Name</div>
        <div role="columnheader" className="px-3">Email</div>
        <div role="columnheader" className="px-3">Role</div>
        <div role="columnheader" className="px-3">Joined</div>
        <div role="columnheader" aria-label="Actions" />
      </div>
      <List
        rowComponent={UserRow}
        rowCount={users.length}
        rowHeight={ROW_HEIGHT}
        rowProps={{
          users,
          selectedIds,
          updatingId,
          currentUserId,
          roleBadgeClass,
          roleDisplayNames,
          onToggleSelect,
          onRoleChange,
          onDeleteUser,
        }}
        style={{ height, width: "100%" }}
        overscanCount={5}
      />
    </div>
  )
}
