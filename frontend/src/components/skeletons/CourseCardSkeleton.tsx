import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

// Mirrors CourseCard exactly (horizontal on sm+, cover-on-left + body
// stack), so the loading grid has the same overall height as the
// loaded grid and nothing jumps when the data lands.
export default function CourseCardSkeleton() {
  return (
    <Card className="flex h-full flex-col overflow-hidden sm:flex-row">
      <Skeleton className="aspect-[21/9] w-full rounded-none sm:aspect-auto sm:h-full sm:min-h-44 sm:w-[38%] sm:max-w-[260px] sm:flex-shrink-0" />
      <div className="flex flex-1 flex-col gap-3 p-6">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-7 w-4/5" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="mt-auto h-4 w-32" />
      </div>
    </Card>
  )
}
