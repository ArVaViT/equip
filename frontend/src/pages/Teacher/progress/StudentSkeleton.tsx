import { Skeleton } from "@/components/ui/skeleton"

/** Animated placeholder shown while student progress loads. */
export function StudentProgressSkeleton() {
  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      <Skeleton className="h-8 w-48 mb-6" />
      <div className="rounded-lg border">
        <div className="p-4 border-b">
          <Skeleton className="h-9 w-64" />
        </div>
        <div className="divide-y">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="p-4 flex items-center gap-4">
              <Skeleton className="h-4 w-4 shrink-0 rounded" />
              <Skeleton className="h-4 flex-1" />
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
