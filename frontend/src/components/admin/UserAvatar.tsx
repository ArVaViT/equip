import { useState } from "react"
import { toProxyImage } from "@/lib/images"
import { cn } from "@/lib/utils"

interface Props {
  /** ``avatar_url`` from the profile. Trimmed and validated; whitespace
   *  or empty string falls through to the initials placeholder. */
  avatarUrl?: string | null
  /** ``full_name`` for the initials fallback. Whitespace-only strings
   *  fall back to the email's first letter so the bubble never renders
   *  blank. */
  fullName?: string | null
  /** Email for the avatar's accessible name and as a second-tier
   *  initials fallback. */
  email: string
  /** Pixel size variant. Two are in use across the admin surface:
   *  ``sm`` = 32 px (table rows), ``md`` = 40 px (mobile cards,
   *  pending-action rows). Defaults to ``sm``. */
  size?: "sm" | "md"
  /** Optional alt-text override. Defaults to ``full_name ?? email``. */
  alt?: string
  className?: string
}

/**
 * Single source of truth for the user-avatar surface across the admin
 * section. Previously this logic was duplicated in 4 places
 * (UsersCard mobile + desktop, VirtualAdminUsers, PendingTeachersCard)
 * with subtly different bugs in each copy:
 *
 *   - Whitespace-only ``full_name`` rendered a blank initials bubble.
 *   - Broken upstream avatar URLs (Google profile pic deleted,
 *     storage expired) rendered the browser's broken-image glyph
 *     instead of falling back to initials.
 *   - Empty-string ``full_name`` returned ``undefined`` from
 *     ``[0]`` and forced the fallback to the second tier; mostly
 *     OK but the four sites disagreed on the order.
 *
 * This component handles all of it. On ``<img onError>`` we flip to
 * the initials bubble so a missing image never shows the glyph.
 */
export function UserAvatar({
  avatarUrl,
  fullName,
  email,
  size = "sm",
  alt,
  className,
}: Props) {
  const [broken, setBroken] = useState(false)
  const trimmedName = fullName?.trim()
  const trimmedUrl = avatarUrl?.trim()
  const dimensionClass = size === "md" ? "h-10 w-10" : "h-8 w-8"
  // Prefer the first non-blank glyph from the name; fall back to the
  // email's first character. ``"?"`` is the last-resort glyph but
  // shouldn't be reachable in practice (email is required at the
  // profile level).
  const initial =
    (trimmedName?.[0] ?? email?.[0] ?? "?").toUpperCase()
  if (trimmedUrl && !broken) {
    return (
      <img
        src={toProxyImage(trimmedUrl)}
        alt={alt ?? (trimmedName || email)}
        loading="lazy"
        onError={() => setBroken(true)}
        className={cn(
          dimensionClass,
          "shrink-0 rounded-full object-cover",
          className,
        )}
      />
    )
  }
  return (
    <div
      className={cn(
        dimensionClass,
        "flex shrink-0 items-center justify-center rounded-full bg-muted font-medium text-muted-foreground",
        size === "md" ? "text-sm" : "text-xs",
        className,
      )}
      aria-hidden
    >
      {initial}
    </div>
  )
}

