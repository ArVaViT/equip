import { Skeleton } from "@/components/ui/skeleton"

/** Centered skeleton shown while the course editor loads. */
export function CourseEditorSkeleton() {
  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <Skeleton className="h-8 w-32 mb-6" />
      <div className="mb-8 overflow-hidden rounded-md border">
        <Skeleton className="h-48 w-full rounded-none" />
        <div className="space-y-3 p-5">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
          <div className="flex gap-2 mt-4">
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-8 w-24" />
            <Skeleton className="h-8 w-24" />
          </div>
        </div>
      </div>
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16 rounded-lg border bg-muted/30" />
        ))}
      </div>
    </div>
  )
}
