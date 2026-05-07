import { useEffect, useState } from "react"
import { Archive, RotateCcw, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import PageSpinner from "@/components/ui/PageSpinner"
import { useConfirm } from "@/components/ui/alert-dialog"
import { coursesService } from "@/services/courses"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import type { Course } from "@/types"
import { formatDate } from "@/i18n/format"

interface Props {
  visible: boolean
  onToggle: () => void
  onRestore: (restored: Course) => void
}

export function TrashSection({ visible, onToggle, onRestore }: Props) {
  const confirm = useConfirm()
  const [trashedCourses, setTrashedCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(false)
  const [restoringId, setRestoringId] = useState<string | null>(null)

  useEffect(() => {
    if (!visible) return
    const signal = { cancelled: false }
    setLoading(true)
    coursesService
      .getTrashedCourses()
      .then((data) => {
        if (!signal.cancelled) setTrashedCourses(data)
      })
      .catch(() => {
        if (!signal.cancelled)
          toast({ title: "Failed to load trash", variant: "destructive" })
      })
      .finally(() => {
        if (!signal.cancelled) setLoading(false)
      })
    return () => {
      signal.cancelled = true
    }
  }, [visible])

  const handleRestore = async (id: string) => {
    setRestoringId(id)
    try {
      const restored = await coursesService.restoreCourse(id)
      setTrashedCourses((prev) => prev.filter((c) => c.id !== id))
      onRestore(restored)
      toast({ title: "Course restored", variant: "success" })
    } catch (err) {
      toast({
        title: getErrorDetail(err, "Failed to restore course"),
        variant: "destructive",
      })
    } finally {
      setRestoringId(null)
    }
  }

  const handlePermanentDelete = async (id: string) => {
    const ok = await confirm({
      title: "Permanently delete this course?",
      description:
        "This will permanently delete the course and all its data (modules, chapters, enrollments, grades). This action cannot be undone.",
      confirmLabel: "Delete permanently",
      tone: "destructive",
    })
    if (!ok) return
    try {
      await coursesService.permanentlyDeleteCourse(id)
      setTrashedCourses((prev) => prev.filter((c) => c.id !== id))
      toast({ title: "Course permanently deleted" })
    } catch (err) {
      toast({
        title: getErrorDetail(err, "Failed to delete course"),
        variant: "destructive",
      })
    }
  }

  return (
    <div className="mt-12 border-t pt-8">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <Archive className="h-4 w-4" />
        {visible ? "Hide Trash" : "Show Trash"}
      </button>

      {visible && (
        <div className="mt-4">
          {loading ? (
            <PageSpinner variant="section" />
          ) : trashedCourses.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">Trash is empty.</p>
          ) : (
            <div className="space-y-3">
              {trashedCourses.map((course) => (
                <Card key={course.id} className="opacity-70 border-dashed">
                  <div className="flex items-center gap-4 p-4">
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-medium truncate">{course.title}</h4>
                      {course.deleted_at && (
                        <p className="text-xs text-muted-foreground">
                          Deleted {formatDate(course.deleted_at)}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleRestore(course.id)}
                        disabled={restoringId === course.id}
                      >
                        <RotateCcw className="h-3.5 w-3.5 mr-1.5" />
                        Restore
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handlePermanentDelete(course.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5 mr-1.5" />
                        Delete Forever
                      </Button>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
