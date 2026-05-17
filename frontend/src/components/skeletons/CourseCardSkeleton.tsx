import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

// Mirrors CourseCard exactly (21:9 cover, eyebrow + big title + body +
// modules line) so the grid doesn't jump when data lands.
export default function CourseCardSkeleton() {
  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <Skeleton className="aspect-[21/9] w-full rounded-none" />
      <div className="flex flex-1 flex-col gap-4 p-5">
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-7 w-4/5" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="mt-auto h-3 w-24" />
      </div>
    </Card>
  )
}
