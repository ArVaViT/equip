import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useSearchParams } from "react-router-dom"
import { useDebouncedSearchParam } from "@/hooks/useDebouncedSearchParam"
import { useAsyncData } from "@/hooks/useAsyncData"
import { coursesService } from "@/services/courses"
import { supabase } from "@/lib/supabase"
import { toast } from "@/lib/toast"
import { getErrorDetail } from "@/lib/errorDetail"
import { useConfirm } from "@/components/ui/alert-dialog"
import { ROLES, type UserRole } from "@/types"
import type { AdminCert } from "./PendingCertsCard"
import { ROLE_I18N_KEY, type AdminStats, type ProfileRow } from "./constants"

const ROLE_FILTER_VALUES = ["admin", "teacher", "pending_teacher", "student"] as const
type RoleFilter = (typeof ROLE_FILTER_VALUES)[number] | ""

function isRoleFilter(v: string): v is (typeof ROLE_FILTER_VALUES)[number] {
  return (ROLE_FILTER_VALUES as readonly string[]).includes(v)
}

interface UseAdminOverviewArgs {
  /** Current signed-in user id — excluded from bulk operations and delete confirmations. */
  currentUserId: string | undefined
  /** When false, the hook skips the data fetch entirely. Used by the
   *  AdminDashboard to avoid pulling users / courses / enrollments
   *  counts when the user opens a tab (cohorts) that needs none of
   *  them. Defaults to true so existing callers don't change shape. */
  enabled?: boolean
}

/**
 * Owns every piece of state rendered by the Overview tab:
 * users list, stats counters, pending-teacher approvals, pending-
 * certificate approvals, the row-selection set, and all bulk/row
 * handlers. Split out of `AdminDashboard` so the page component stays
 * focused on layout and tab routing.
 */
export function useAdminOverview({ currentUserId, enabled = true }: UseAdminOverviewArgs) {
  const confirm = useConfirm()
  const { t } = useTranslation()
  const [params, setParams] = useSearchParams()

  const {
    input: searchInput,
    setInput: setSearchInput,
    value: urlQuery,
    maxLength: searchMaxLength,
  } = useDebouncedSearchParam()

  // URL-state role filter so a bookmarked admin link round-trips with
  // its filter. Reject any value not in the allow-list (defaults to "").
  const rawRoleFilter = params.get("role") ?? ""
  const roleFilter: RoleFilter = isRoleFilter(rawRoleFilter) ? rawRoleFilter : ""
  const setRoleFilter = useCallback(
    (next: RoleFilter) => {
      setParams(
        (prev) => {
          const n = new URLSearchParams(prev)
          if (next) n.set("role", next)
          else n.delete("role")
          return n
        },
        { replace: true },
      )
    },
    [setParams],
  )

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
      // Hook is reused across tabs that don't all need this data; the
      // ``enabled`` arg lets the parent skip the fetch (and the loading
      // state) without unmounting the hook.
      if (!enabled) return undefined
      const [allUsers, coursesCount, enrollmentsCount, certs] = await Promise.all([
        coursesService.getAllUsers(),
        supabase.from("courses").select("id", { count: "exact", head: true }),
        supabase.from("enrollments").select("id", { count: "exact", head: true }),
        coursesService.getAdminPendingCerts().catch(() => []),
      ])
      if (isCancelled()) return undefined
      return { allUsers, coursesCount, enrollmentsCount, certs }
    },
    [reloadKey, enabled],
  )

  // Sync fetched data into individual state (handlers still need setUsers/setAdminCerts)
  useEffect(() => {
    if (!fetchedData) return
    const { allUsers, coursesCount, enrollmentsCount, certs } = fetchedData
    setUsers(allUsers as ProfileRow[])
    // ``Last 7 days`` is a client-side roll-up of the already-loaded
    // user list so the overview doesn't pay for an extra API call.
    // The window anchors at "now - 7d" each render — good enough for
    // a rough trend, and cheap.
    const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
    const usersLast7Days = (allUsers as ProfileRow[]).filter(
      (u) => new Date(u.created_at).getTime() >= sevenDaysAgo,
    ).length
    setStats({
      users: allUsers.length,
      courses: coursesCount.count ?? 0,
      enrollments: enrollmentsCount.count ?? 0,
      usersLast7Days,
    })
    setAdminCerts(certs)
  }, [fetchedData])

  // Surface a friendly fallback to the rest of the hook's `error: string | null`
  // contract — AdminDashboard renders this verbatim in <ErrorState>, so we
  // never want a raw axios / supabase message bleeding into the UI.
  const error = fetchError ? t("admin.overview.loadError") : null

  const filtered = useMemo(() => {
    const q = urlQuery.trim().toLowerCase()
    return users.filter((u) => {
      if (roleFilter && u.role !== roleFilter) return false
      if (q && !u.full_name?.toLowerCase().includes(q) && !u.email.toLowerCase().includes(q)) {
        return false
      }
      return true
    })
  }, [users, urlQuery, roleFilter])

  /**
   * Per-role counts across the whole user list (NOT filtered) — drives
   * the chip strip above the search input so the admin sees the
   * tenant's role distribution at a glance without flipping the
   * filter through every value.
   */
  const roleCounts = useMemo(() => {
    const counts: Record<UserRole, number> = {
      admin: 0,
      teacher: 0,
      pending_teacher: 0,
      student: 0,
    }
    for (const u of users) {
      if (u.role in counts) counts[u.role as UserRole] += 1
    }
    return counts
  }, [users])

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
      toast({ title: t("admin.overview.toast.roleUpdated"), variant: "success" })
    } catch {
      toast({ title: t("admin.overview.toast.roleUpdateFailed"), variant: "destructive" })
    } finally {
      setUpdatingId(null)
    }
  }

  const handleDeleteUser = async (target: ProfileRow) => {
    // Fence the self-delete path. The UI button is already disabled
    // for the signed-in admin, but the hook is callable from any
    // future surface (a keyboard shortcut, an API console) and the
    // server-side check shouldn't be the only thing standing between
    // an admin and locking themselves out of their tenant.
    if (target.id === currentUserId) {
      toast({
        title: t("admin.overview.toast.cannotDeleteSelf"),
        variant: "destructive",
      })
      return
    }
    const ok = await confirm({
      title: t("admin.overview.confirm.deleteUserTitle", { name: target.full_name || target.email }),
      description: t("admin.overview.confirm.deleteUserDescription"),
      confirmLabel: t("admin.overview.confirm.deleteUserAction"),
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
      toast({ title: t("admin.overview.toast.userDeleted"), variant: "success" })
    } catch (err) {
      toast({
        title: getErrorDetail(err, t("admin.overview.toast.deleteUserFailed")),
        variant: "destructive",
      })
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
    const localizedRole = t(ROLE_I18N_KEY[bulkRole])
    const ok = await confirm({
      title: t("admin.overview.confirm.bulkRoleTitle"),
      description: t("admin.overview.confirm.bulkRoleDescription", {
        count: ids.length,
        role: localizedRole,
      }),
      confirmLabel: t("admin.overview.confirm.bulkRoleAction"),
    })
    if (!ok) return
    setBulkUpdating(true)
    try {
      const result = await coursesService.bulkUpdateUserRoles(ids, bulkRole)
      setUsers((prev) =>
        prev.map((u) => (ids.includes(u.id) ? { ...u, role: bulkRole } : u)),
      )
      setSelectedIds(new Set())
      toast({
        title: t("admin.overview.toast.bulkUpdated", {
          count: result.updated,
          role: localizedRole,
        }),
        variant: "success",
      })
    } catch (err) {
      toast({
        title: getErrorDetail(err, t("admin.overview.toast.bulkUpdateFailed")),
        variant: "destructive",
      })
    } finally {
      setBulkUpdating(false)
    }
  }

  const pendingTeachers = useMemo(
    () => users.filter((u) => u.role === ROLES.PENDING_TEACHER),
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
    const name = u.full_name || u.email
    const ok = await confirm({
      title: t("admin.pendingTeachers.confirm.approveTitle"),
      description: t("admin.pendingTeachers.confirm.approveDescription", { name }),
      confirmLabel: t("admin.pendingTeachers.confirm.approveAction"),
    })
    if (ok)
      await setTeacherRole(
        u.id,
        "teacher",
        t("admin.pendingTeachers.toast.approved"),
        t("admin.pendingTeachers.toast.approveFailed"),
      )
  }

  const denyPendingTeacher = async (u: ProfileRow) => {
    const name = u.full_name || u.email
    const ok = await confirm({
      title: t("admin.pendingTeachers.confirm.denyTitle"),
      description: t("admin.pendingTeachers.confirm.denyDescription", { name }),
      confirmLabel: t("admin.pendingTeachers.confirm.denyAction"),
      tone: "destructive",
    })
    if (ok)
      await setTeacherRole(
        u.id,
        "student",
        t("admin.pendingTeachers.toast.denied"),
        t("admin.pendingTeachers.toast.denyFailed"),
      )
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
      t("admin.pendingCerts.toast.approved"),
      t("admin.pendingCerts.toast.approveFailed"),
    )

  const handleRejectCert = (certId: string) =>
    handleCertDecision(
      certId,
      () => coursesService.rejectCert(certId),
      t("admin.pendingCerts.toast.rejected"),
      t("admin.pendingCerts.toast.rejectFailed"),
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
    roleFilter,
    setRoleFilter,
    roleCounts,
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
