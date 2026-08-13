import { Skeleton } from "@/components/ui/skeleton"

/**
 * The shape of a chapter while its blocks are on the wire.
 *
 * This was a centred spinner. A ring tells the reader that something is
 * happening and nothing about what; then the text arrives and the page jumps.
 * On the reading surface — the one screen this product exists to serve, and
 * the one people open on a phone over a slow connection — that jump is the
 * whole experience of arriving.
 *
 * A skeleton is not a nicer spinner. It is a promise about layout: these bars
 * sit at the measure and the leading the prose will use, so the text lands
 * where the placeholder was and nothing moves.
 *
 * The bar widths are uneven on purpose. A stack of identical full-width bars
 * reads as a table; prose has a ragged right edge, and the eye recognises the
 * silhouette of a paragraph before it can read a word of it.
 */
export function ReadingSkeleton() {
  return (
    <div aria-busy="true" className="space-y-8">
      <div className="space-y-3">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-4 w-32" />
      </div>
      {[0, 1].map((paragraph) => (
        <div key={paragraph} className="space-y-3">
          {["w-full", "w-full", "w-11/12", "w-4/5"].map((width, line) => (
            <Skeleton key={line} className={`h-[1.0625rem] ${width}`} />
          ))}
        </div>
      ))}
    </div>
  )
}
