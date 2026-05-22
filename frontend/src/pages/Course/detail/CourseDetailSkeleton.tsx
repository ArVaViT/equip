import { Skeleton } from "@/components/ui/skeleton"

export function CourseDetailSkeleton() {
  return (
    <div className="container mx-auto px-4 py-6 max-w-4xl">
      <Skeleton className="h-8 w-24 mb-4" />
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <Skeleton className="w-full sm:w-36 h-24 rounded-lg shrink-0" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-7 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </div>
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16 rounded-lg" />
        ))}
      </div>
    </div>
  )
}
