import { forwardRef } from "react"
import { useTranslation } from "react-i18next"
import { AlertCircle, Bell, CheckCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import PageSpinner from "@/components/ui/PageSpinner"
import { cn } from "@/lib/utils"
import type { Notification } from "@/types"
import { NotificationItem } from "./NotificationItem"

interface Props {
  notifications: Notification[]
  unreadCount: number
  loading: boolean
  loadingMore: boolean
  loadError: boolean
  hasMore: boolean
  onActivate: (n: Notification) => void
  onDelete: (id: string) => void
  onMarkAllRead: () => void
  onLoadMore: () => void
  onRetry: () => void
  /** Narrow sheet / drawer: full-width panel below the bell so it does not overflow horizontally. */
  variant?: "popover" | "sheet"
}

/**
 * Drop-down panel anchored below the bell. Purely presentational — all
 * state lives in `useNotifications` and is handed in via props.
 */
export const NotificationPanel = forwardRef<HTMLDivElement, Props>(
  function NotificationPanel(
    {
      notifications,
      unreadCount,
      loading,
      loadingMore,
      loadError,
      hasMore,
      onActivate,
      onDelete,
      onMarkAllRead,
      onLoadMore,
      onRetry,
      variant = "popover",
    },
    ref,
  ) {
    const { t } = useTranslation()
    const isSheet = variant === "sheet"

    return (
      <div
        ref={ref}
        role="region"
        aria-label={t("notifications.panelAriaLabel")}
        className={cn(
          "mt-2 overflow-hidden rounded-lg shadow-lg",
          // Sheet variant: live in the flex flow so it pushes the
          // "Profile" link below it instead of floating over the next
          // nav row as a phantom overlay (the original
          // ``absolute top-full`` covered every menu item under the
          // bell in the mobile sheet — what Vadym called the overlay
          // "помимо основного пункта"). Solid background here is fine
          // because the mobile sheet already has its own backdrop.
          //
          // Popover variant: still anchored absolutely over the page
          // content. The frosted layer separates the dropdown from the
          // busy course/admin pages it floats over.
          isSheet
            ? "w-full bg-surface"
            : "absolute right-0 top-full z-50 w-80 bg-surface/85 backdrop-blur-md sm:w-96 supports-[backdrop-filter]:bg-surface/75",
        )}
      >
        <div className="flex items-center justify-between border-b border-edge px-4 py-3">
          <h3 className="text-sm font-semibold text-ink">{t("notifications.title")}</h3>
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={onMarkAllRead}
              className="flex items-center gap-1 text-xs text-ink-muted transition-colors hover:text-ink"
            >
              <CheckCheck className="h-3.5 w-3.5" strokeWidth={1.75} />
              {t("notifications.markAllRead")}
            </button>
          )}
        </div>

        <div
          className={cn(
            "overflow-y-auto",
            isSheet ? "max-h-[min(380px,50dvh)]" : "max-h-[400px]",
          )}
        >
          {loading ? (
            <PageSpinner variant="section" />
          ) : loadError ? (
            <div className="flex flex-col items-center gap-2 py-10 text-ink-muted">
              <AlertCircle className="h-8 w-8 text-destructive/70" strokeWidth={1.75} />
              <p className="text-sm text-destructive">{t("notifications.loadFailed")}</p>
              <button
                type="button"
                onClick={onRetry}
                className="text-xs text-brand hover:underline"
              >
                {t("notifications.tryAgain")}
              </button>
            </div>
          ) : notifications.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-10 text-ink-muted">
              <Bell className="h-8 w-8 opacity-30" strokeWidth={1.75} />
              <p className="text-sm">{t("notifications.empty")}</p>
            </div>
          ) : (
            <>
              {notifications.map((n) => (
                <NotificationItem
                  key={n.id}
                  notification={n}
                  onActivate={onActivate}
                  onDelete={onDelete}
                />
              ))}
              {hasMore && (
                <div className="border-t border-edge/50 p-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="w-full text-xs"
                    disabled={loadingMore}
                    onClick={onLoadMore}
                  >
                    {loadingMore ? t("notifications.loadingMore") : t("notifications.loadMore")}
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    )
  },
)
