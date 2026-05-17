import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

// Mirrors the CourseCard row shape exactly (56-64px thumbnail + title +
// description + meta), so the loading list doesn't jump when data lands.
export default function CourseCardSkeleton() {
  return (
    <Card className="flex items-stretch gap-4 p-4 sm:items-center sm:gap-5">
      <Skeleton className="h-14 w-14 shrink-0 rounded-md sm:h-16 sm:w-16" />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <Skeleton className="h-4 w-3/5" />
        <Skeleton className="h-3.5 w-4/5" />
        <Skeleton className="mt-1 h-3 w-32" />
      </div>
    </Card>
  )
}
