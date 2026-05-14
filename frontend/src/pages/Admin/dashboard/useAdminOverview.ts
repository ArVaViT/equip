import { useCallback, useEffect, useMemo, useState } from "react"
import { useDebouncedSearchParam } from "@/hooks/useDebouncedSearchParam"
import { useAsyncData } from "@/hooks/useAsyncData"
import { coursesService } from "@/services/courses"
import { supabase } from "@/lib/supabase"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import { useConfirm } from "@/components/ui/alert-dialog"
import type { UserRole } from "@/types"
import type { AdminCert } from "./PendingCertsCard"
import type { AdminStats, ProfileRow } from "./constants"

interface UseAdminOverviewArgs {
  /** Current signed-in user id — excluded from bulk operations and delete confirmations. */
  currentUserId: string | undefined
}

/**
 * Owns every piece of state rendered by the Overview tab:
 * users list, stats counters, pending-teacher approvals, pending-
 * certificate approvals, the row-selection set, and all bulk/row
 * handlers. Split out of `AdminDashboard` so the page component stays
 * focused on layout and tab routing.
 */
export function useAdminOverview({ currentUserId }: UseAdminOverviewArgs) {
  const confirm = useConfirm()

  const {
    input: searchInput,
    setInput: setSearchInput,
    value: urlQuery,
    maxLength: searchMaxLength,
  } = useDebouncedSearchParam()

  const [users, setUsers] = useState<ProfileRow[]>([])
  const [stats, setStats] = useState<AdminStats>({ users: 0, courses: 0, enrollments: 0 })
  const [adminCerts, setAdminCerts] = useState<AdminCert[]>([])
  const [updatingId, setUpdatingId] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [bulkRole, setBulkRole] = useState<UserRole>("student")
  const [bulkUpdating, setBulkUpdating] = useState(false)
  const [certActionId, setCertActionId] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])

  const { data: fetchedData, loading, error: fetchError } = useAsyncData(
    async (isCancelled) => {
      const [allUsers, coursesCount, enrollmentsCount, certs] = await Promise.all([
        coursesService.getAllUsers(),
        supabase.from("courses").select("id", { count: "exact", head: true }),
        supabase.from("enrollments").select("id", { count: "exact", head: true }),
        coursesService.getAdminPendingCerts().catch(() => []),
      ])
      if (isCancelled()) return undefined
      return { allUsers, coursesCount, enrollmentsCount, certs }
    },
    [reloadKey],
  )

  // Sync fetched data into individual state (handlers still need setUsers/setAdminCerts)
  useEffect(() => {
    if (!fetchedData) return
    const { allUsers, coursesCount, enrollmentsCount, certs } = fetchedData
    setUsers(allUsers as ProfileRow[])
    setStats({
      users: allUsers.length,
      courses: coursesCount.count ?? 0,
      enrollments: enrollmentsCount.count ?? 0,
    })
    setAdminCerts(certs)
  }, [fetchedData])

  // Surface a friendly fallback to the rest of the hook's `error: string | null`
  // contract — AdminDashboard renders this verbatim in <ErrorState>, so we
  // never want a raw axios / supabase message bleeding into the UI.
  const error = fetchError ? "Failed to load admin data. Please try again." : null

  const filtered = useMemo(() => {
    const q = urlQuery.trim().toLowerCase()
    if (!q) return users
    return users.filter(
      (u) => u.full_name?.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
    )
  }, [users, urlQuery])

  const userMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const u of users) map[u.id] = u.full_name || u.email
    return map
  }, [users])

  // When a filter hides rows, drop them from the selection so
  // "Apply to N selected" counts only visible rows.
  const filteredIds = useMemo(() => new Set(filtered.map((u) => u.id)), [filtered])
  useEffect(() => {
    setSelectedIds((prev) => {
      const narrowed = new Set([...prev].filter((id) => filteredIds.has(id)))
      return narrowed.size === prev.size ? prev : narrowed
    })
  }, [filteredIds])

  const handleRoleChange = async (userId: string, newRole: UserRole) => {
    setUpdatingId(userId)
    try {
      await coursesService.updateUserRole(userId, newRole)
      setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, role: newRole } : u)))
      toast({ title: "Role updated", variant: "success" })
    } catch {
      toast({ title: "Failed to update role", variant: "destructive" })
    } finally {
      setUpdatingId(null)
    }
  }

  const handleDeleteUser = async (target: ProfileRow) => {
    const ok = await confirm({
      title: `Delete ${target.full_name || target.email}?`,
      description:
        "This permanently removes their account, enrollments, submissions, grades, certificates, and notifications. Courses they created will be kept but disassociated. This cannot be undone.",
      confirmLabel: "Delete account",
      tone: "destructive",
    })
    if (!ok) return
    setUpdatingId(target.id)
    try {
      await coursesService.adminDeleteUser(target.id)
      setUsers((prev) => prev.filter((u) => u.id !== target.id))
      setSelectedIds((prev) => {
        if (!prev.has(target.id)) return prev
        const next = new Set(prev)
        next.delete(target.id)
        return next
      })
      toast({ title: "User deleted", variant: "success" })
    } catch (err) {
      toast({ title: getErrorDetail(err, "Failed to delete user"), variant: "destructive" })
    } finally {
      setUpdatingId(null)
    }
  }

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    const allFilteredSelected =
      filtered.length > 0 && filtered.every((u) => selectedIds.has(u.id))
    if (allFilteredSelected) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filtered.map((u) => u.id)))
    }
  }

  const clearSelection = () => setSelectedIds(new Set())

  const handleBulkRoleChange = async () => {
    // Never flip our own role in a bulk update — an admin deselecting
    // themselves mid-action would lock them out.
    const ids = [...selectedIds].filter((id) => id !== currentUserId)
    if (ids.length === 0) return
    const ok = await confirm({
      title: "Change role for selected users?",
      description: `${ids.length} user(s) will be set to role "${bulkRole}".`,
      confirmLabel: "Apply",
    })
    if (!ok) return
    setBulkUpdating(true)
    try {
      const result = await coursesService.bulkUpdateUserRoles(ids, bulkRole)
      setUsers((prev) =>
        prev.map((u) => (ids.includes(u.id) ? { ...u, role: bulkRole } : u)),
      )
      setSelectedIds(new Set())
      toast({ title: `Updated ${result.updated} user(s) to ${bulkRole}`, variant: "success" })
    } catch (err) {
      toast({ title: getErrorDetail(err, "Bulk update failed"), variant: "destructive" })
    } finally {
      setBulkUpdating(false)
    }
  }

  const pendingTeachers = useMemo(
    () => users.filter((u) => u.role === "pending_teacher"),
    [users],
  )

  const setTeacherRole = async (userId: string, nextRole: UserRole, okMsg: string, failMsg: string) => {
    setUpdatingId(userId)
    try {
      await coursesService.updateUserRole(userId, nextRole)
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, role: nextRole } : u)),
      )
      toast({ title: okMsg, variant: "success" })
    } catch {
      toast({ title: failMsg, variant: "destructive" })
    } finally {
      setUpdatingId(null)
    }
  }

  const approvePendingTeacher = async (u: ProfileRow) => {
    const ok = await confirm({
      title: "Approve this teacher?",
      description: `${u.full_name || u.email} will gain access to teacher features.`,
      confirmLabel: "Approve",
    })
    if (ok) await setTeacherRole(u.id, "teacher", "Teacher approved", "Failed to approve teacher")
  }

  const denyPendingTeacher = async (u: ProfileRow) => {
    const ok = await confirm({
      title: "Deny this teacher?",
      description: `${u.full_name || u.email}'s teacher request will be rejected.`,
      confirmLabel: "Deny",
      tone: "destructive",
    })
    if (ok) await setTeacherRole(u.id, "student", "Teacher denied", "Failed to deny teacher")
  }

  const handleCertDecision = async (
    certId: string,
    call: () => Promise<unknown>,
    okMsg: string,
    failMsg: string,
  ) => {
    setCertActionId(certId)
    try {
      await call()
      setAdminCerts((prev) => prev.filter((c) => c.id !== certId))
      toast({ title: okMsg, variant: "success" })
    } catch {
      toast({ title: failMsg, variant: "destructive" })
    } finally {
      setCertActionId(null)
    }
  }

  const handleFinalApproveCert = (certId: string) =>
    handleCertDecision(
      certId,
      () => coursesService.adminApproveCert(certId),
      "Certificate approved",
      "Failed to approve certificate",
    )

  const handleRejectCert = (certId: string) =>
    handleCertDecision(
      certId,
      () => coursesService.rejectCert(certId),
      "Certificate rejected",
      "Failed to reject certificate",
    )

  return {
    users,
    filtered,
    userMap,
    stats,
    adminCerts,
    pendingTeachers,
    loading,
    error,
    updatingId,
    selectedIds,
    bulkRole,
    bulkUpdating,
    certActionId,
    searchInput,
    setSearchInput,
    urlQuery,
    searchMaxLength,
    reload,
    setBulkRole,
    handleRoleChange,
    handleDeleteUser,
    toggleSelect,
    toggleSelectAll,
    clearSelection,
    handleBulkRoleChange,
    approvePendingTeacher,
    denyPendingTeacher,
    handleFinalApproveCert,
    handleRejectCert,
  }
}
