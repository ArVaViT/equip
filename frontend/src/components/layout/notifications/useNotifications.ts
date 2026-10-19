import { useCallback, useEffect, useRef, useState } from "react"
import type { Notification } from "@/types"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"

/**
 * Polling interval for the unread-count badge. Short enough that a newly
 * arrived notification surfaces in roughly a minute, long enough that the
 * endpoint doesn't burn through a serverless function's budget.
 */
const UNREAD_POLL_MS = 30_000

/**
 * How long we trust a cached first page of notifications before re-fetching
 * on the next `open`. Keeping this equal to the unread-poll keeps the list
 * and badge from drifting too far out of sync.
 */
const LIST_STALE_MS = 30_000

type CancelSignal = { cancelled: boolean }

/**
 * Encapsulates every piece of runtime state the notification bell needs:
 *
 * - unread-count polling (with visibility-aware interval),
 * - lazy first-page load on open,
 * - paginated "load more",
 * - optimistic mark-read / mark-all / delete.
 *
 * The dropdown panel stays a pure view over this hook's return value.
 */
export function useNotifications(open: boolean) {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)

  const loadMoreSignalRef = useRef<CancelSignal | null>(null)
  const lastFetchedAtRef = useRef<number>(0)

  const fetchUnreadCount = useCallback(async (signal?: CancelSignal) => {
    try {
      const count = await coursesService.getUnreadCount()
      if (!signal?.cancelled) setUnreadCount(count)
    } catch {
      // Polling failure is non-critical; will retry on next interval.
    }
  }, [])

  const fetchNotifications = useCallback(
    async (pageNum: number, signal?: CancelSignal) => {
      if (pageNum === 1) {
        setLoading(true)
        setLoadError(false)
      } else {
        setLoadingMore(true)
      }
      try {
        const res = await coursesService.getNotifications(pageNum)
        if (!signal?.cancelled) {
          setNotifications((prev) =>
            pageNum === 1 ? res.items : [...prev, ...res.items],
          )
          setPage(pageNum)
          setHasMore(pageNum * res.page_size < res.total)
        }
      } catch {
        // First-page failure = error state. Later-page failures leave the
        // existing list alone so the user still sees what we already have.
        if (!signal?.cancelled && pageNum === 1) setLoadError(true)
      } finally {
        if (!signal?.cancelled) {
          if (pageNum === 1) setLoading(false)
          else setLoadingMore(false)
        }
      }
    },
    [],
  )

  // Background unread-count poll, paused while the tab is hidden.
  useEffect(() => {
    const signal: CancelSignal = { cancelled: false }
    fetchUnreadCount(signal)

    let interval: ReturnType<typeof setInterval> | null = null
    const start = () => {
      if (interval == null) {
        interval = setInterval(() => fetchUnreadCount(signal), UNREAD_POLL_MS)
      }
    }
    const stop = () => {
      if (interval != null) {
        clearInterval(interval)
        interval = null
      }
    }
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        fetchUnreadCount(signal)
        start()
      } else {
        stop()
      }
    }

    if (document.visibilityState === "visible") start()
    document.addEventListener("visibilitychange", onVisibility)

    return () => {
      signal.cancelled = true
      stop()
      document.removeEventListener("visibilitychange", onVisibility)
    }
  }, [fetchUnreadCount])

  // Load the first page when the panel opens (or refresh if it's stale);
  // cancel an in-flight "load more" when it closes so we don't append to
  // stale state after re-opening.
  useEffect(() => {
    if (!open) {
      setLoadingMore(false)
      if (loadMoreSignalRef.current) loadMoreSignalRef.current.cancelled = true
      return
    }
    const signal: CancelSignal = { cancelled: false }
    const isStale = Date.now() - lastFetchedAtRef.current > LIST_STALE_MS
    if (notifications.length === 0 || isStale) {
      void fetchNotifications(1, signal).then(() => {
        if (!signal.cancelled) lastFetchedAtRef.current = Date.now()
      })
    }
    return () => {
      signal.cancelled = true
      if (loadMoreSignalRef.current) loadMoreSignalRef.current.cancelled = true
    }
    // Intentionally omitting `notifications.length` — we only refresh on
    // open/close transitions, not on every mutation of the list itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, fetchNotifications])

  const loadMore = useCallback(() => {
    if (loadMoreSignalRef.current) loadMoreSignalRef.current.cancelled = true
    const signal: CancelSignal = { cancelled: false }
    loadMoreSignalRef.current = signal
    void fetchNotifications(page + 1, signal)
  }, [fetchNotifications, page])

  const retry = useCallback(() => {
    void fetchNotifications(1)
  }, [fetchNotifications])

  const markRead = useCallback(async (id: string) => {
    try {
      await coursesService.markAsRead(id)
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)),
      )
      setUnreadCount((prev) => Math.max(0, prev - 1))
    } catch {
      // Optimistic UI — navigation still happens even if the mark fails.
    }
  }, [])

  const markAllRead = useCallback(async () => {
    try {
      await coursesService.markAllAsRead()
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
      setUnreadCount(0)
    } catch (err) {
      // Nothing moved on screen, which is right — but a press that does
      // nothing, silently, reads as a broken button.
      toast({ title: getErrorDetail(err), variant: "destructive" })
    }
  }, [])

  const remove = useCallback(async (id: string) => {
    try {
      await coursesService.deleteNotification(id)
      setNotifications((prev) => {
        const removed = prev.find((n) => n.id === id)
        if (removed && !removed.is_read) {
          setUnreadCount((c) => Math.max(0, c - 1))
        }
        return prev.filter((n) => n.id !== id)
      })
    } catch (err) {
      // The notification stays; say why.
      toast({ title: getErrorDetail(err), variant: "destructive" })
    }
  }, [])

  return {
    notifications,
    unreadCount,
    loading,
    loadingMore,
    loadError,
    hasMore,
    loadMore,
    retry,
    markRead,
    markAllRead,
    remove,
  }
}
