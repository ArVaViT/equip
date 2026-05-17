import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

export default function CourseCardSkeleton() {
  return (
    <Card className="flex flex-col overflow-hidden">
      <Skeleton className="w-full h-44 rounded-none" />
      <CardHeader className="pb-2">
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-3 w-full mt-2" />
        <Skeleton className="h-3 w-2/3 mt-1" />
      </CardHeader>
      <CardContent className="mt-auto pt-2">
        <div className="flex items-center justify-between">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-8 w-16" />
        </div>
      </CardContent>
    </Card>
  )
}
