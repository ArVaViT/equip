import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
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
  const { t } = useTranslation()
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
          toast({ title: t("teacherDashboard.trash.loadFailed"), variant: "destructive" })
      })
      .finally(() => {
        if (!signal.cancelled) setLoading(false)
      })
    return () => {
      signal.cancelled = true
    }
  }, [visible, t])

  const handleRestore = async (id: string) => {
    setRestoringId(id)
    try {
      const restored = await coursesService.restoreCourse(id)
      setTrashedCourses((prev) => prev.filter((c) => c.id !== id))
      onRestore(restored)
      toast({ title: t("teacherDashboard.trash.restored"), variant: "success" })
    } catch (err) {
      toast({
        title: getErrorDetail(err, t("teacherDashboard.trash.restoreFailed")),
        variant: "destructive",
      })
    } finally {
      setRestoringId(null)
    }
  }

  const handlePermanentDelete = async (id: string) => {
    const ok = await confirm({
      title: t("teacherDashboard.trash.confirmDelete.title"),
      description: t("teacherDashboard.trash.confirmDelete.description"),
      confirmLabel: t("teacherDashboard.trash.confirmDelete.confirm"),
      tone: "destructive",
    })
    if (!ok) return
    try {
      await coursesService.permanentlyDeleteCourse(id)
      setTrashedCourses((prev) => prev.filter((c) => c.id !== id))
      toast({ title: t("teacherDashboard.trash.deleted") })
    } catch (err) {
      toast({
        title: getErrorDetail(err, t("teacherDashboard.trash.deleteFailed")),
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
        <Archive className="h-4 w-4" strokeWidth={1.75} />
        {visible
          ? t("teacherDashboard.trash.hide")
          : t("teacherDashboard.trash.show")}
      </button>

      {visible && (
        <div className="mt-4">
          {loading ? (
            <PageSpinner variant="section" />
          ) : trashedCourses.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4">
              {t("teacherDashboard.trash.empty")}
            </p>
          ) : (
            <div className="space-y-3">
              {trashedCourses.map((course) => (
                <Card key={course.id} className="opacity-70 border-dashed">
                  <div className="flex items-center gap-4 p-4">
                    <div className="flex-1 min-w-0">
                      <h4 className="text-sm font-medium truncate">{course.title}</h4>
                      {course.deleted_at && (
                        <p className="text-xs text-muted-foreground">
                          {t("teacherDashboard.trash.deletedAt", {
                            date: formatDate(course.deleted_at),
                          })}
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
                        <RotateCcw className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
                        {t("teacherDashboard.trash.restore")}
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handlePermanentDelete(course.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
                        {t("teacherDashboard.trash.deleteForever")}
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
