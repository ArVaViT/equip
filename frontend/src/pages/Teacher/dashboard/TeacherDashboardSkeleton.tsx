import { Skeleton } from "@/components/ui/skeleton"
import { Card } from "@/components/ui/card"

/**
 * Animated placeholder shown while the teacher dashboard course list
 * loads. Mirrors the real {@link CourseCard} layout so the page does
 * not jump when data arrives.
 */
export function TeacherDashboardSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <Card key={i}>
          <div className="flex items-start gap-4 p-5">
            <Skeleton className="h-20 w-20 shrink-0 rounded-lg" />
            <div className="flex-1 min-w-0 space-y-3">
              <div className="flex items-center gap-2">
                <Skeleton className="h-5 w-1/3" />
                <Skeleton className="h-5 w-16 rounded-full" />
              </div>
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-2/5" />
              <div className="flex items-center gap-4 pt-1">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="h-3 w-28" />
              </div>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              {[0, 1, 2, 3].map((j) => (
                <Skeleton key={j} className="h-8 w-8 rounded-md" />
              ))}
            </div>
          </div>
        </Card>
      ))}
    </div>
  )
}
