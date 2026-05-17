import { Card } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

// Mirrors the CourseCard structure exactly so the loading state has the
// same overall height + aspect ratio + spacing as the loaded state —
// otherwise the grid jumps when the data lands.
export default function CourseCardSkeleton() {
  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <Skeleton className="aspect-[16/9] w-full rounded-none" />
      <div className="flex flex-1 flex-col gap-3 p-5">
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
        <div className="mt-auto flex items-center gap-3 pt-2">
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-5 w-20 rounded-full" />
        </div>
      </div>
    </Card>
  )
}
