import { toProxyImage } from "@/lib/images"
import { organizationInitials } from "@/lib/organizationInitials"
import { cn } from "@/lib/utils"

/**
 * An organization's face: its logo, or its initials in the place a logo goes.
 *
 * One component for every place an organization is named next to a picture —
 * the showcase, its own page, a member's profile and courses, a course's
 * author, an invitation — so a logo uploaded once shows everywhere at once
 * and an organization without one looks the same everywhere too. Square with
 * rounded corners, not round like a person: a logo is drawn to its own
 * edges, and a circle crops the corners of most of them.
 *
 * Decorative (`alt=""`, `aria-hidden` initials): the name is always printed
 * beside it, and a screen reader that read both would say the name twice.
 */
const SIZES = {
  xs: "h-6 w-6 rounded text-[0.625rem]",
  sm: "h-10 w-10 rounded-md text-base",
  md: "h-14 w-14 rounded-lg text-xl",
  lg: "h-20 w-20 rounded-card text-3xl",
} as const

export type OrganizationMarkSize = keyof typeof SIZES

export function OrganizationMark({
  name,
  logoUrl,
  size = "md",
  className,
}: {
  name: string
  logoUrl: string | null | undefined
  size?: OrganizationMarkSize
  className?: string
}) {
  const src = toProxyImage(logoUrl)
  const box = cn("shrink-0 border border-edge", SIZES[size], className)
  if (src) {
    // `object-contain` on the surface colour: a wide wordmark sits whole in
    // the square instead of losing its ends, and a transparent PNG reads on
    // both themes.
    return <img src={src} alt="" loading="lazy" decoding="async" className={cn(box, "bg-surface object-contain")} />
  }
  return (
    <span
      aria-hidden
      className={cn(box, "flex items-center justify-center bg-muted/40 font-serif font-semibold leading-none text-ink-muted")}
    >
      {organizationInitials(name)}
    </span>
  )
}
