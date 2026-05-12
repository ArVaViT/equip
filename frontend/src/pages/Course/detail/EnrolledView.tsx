import { useCallback, useState } from "react"
import { Paperclip, Star } from "lucide-react"
import { Button } from "@/components/ui/button"
import CourseAnnouncements from "@/components/announcements/CourseAnnouncements"
import CourseReviews from "@/components/course/CourseReviews"
import CertificateCard from "@/components/course/CertificateCard"
import { Modal } from "@/components/patterns"
import { storageService } from "@/services/storage"
import { toast } from "@/lib/toast"
import type {
  CalendarEvent,
  Certificate,
  Cohort,
  Course,
  Enrollment,
  Module,
} from "@/types"
import type { CourseMaterial } from "./types"
import { EnrolledHeader } from "./EnrolledHeader"
import { MaterialsModal } from "./MaterialsModal"
import { ModuleList } from "./ModuleList"
import { UpcomingEvents } from "./UpcomingEvents"

interface Props {
  course: Course
  enrollment: Enrollment
  cohorts: Cohort[]
  sortedModules: Module[]
  totalChapters: number
  completedChapterIds: Set<string>
  materials: CourseMaterial[]
  calendarEvents: CalendarEvent[]
  certificate: Certificate | null
  onCertificateUpdate: (cert: Certificate | null) => void
}

export function EnrolledView({
  course,
  enrollment,
  cohorts,
  sortedModules,
  totalChapters,
  completedChapterIds,
  materials,
  calendarEvents,
  certificate,
  onCertificateUpdate,
}: Props) {
  const [materialsModal, setMaterialsModal] = useState(false)
  const [reviewsModal, setReviewsModal] = useState(false)
  const [downloadingPath, setDownloadingPath] = useState<string | null>(null)

  const enrolledCohort = cohorts.find((c) => c.id === enrollment.cohort_id)

  const handleDownload = useCallback(async (path: string) => {
    setDownloadingPath(path)
    try {
      const url = await storageService.getSignedMaterialUrl(path)
      window.open(url, "_blank", "noopener,noreferrer")
    } catch {
      toast({ title: "Failed to download file", variant: "destructive" })
    } finally {
      setDownloadingPath(null)
    }
  }, [])

  return (
    <div className="animate-fade-in container mx-auto px-4 py-6 max-w-4xl">
      <EnrolledHeader
        course={course}
        enrollment={enrollment}
        enrolledCohort={enrolledCohort}
        moduleCount={sortedModules.length}
        chapterCount={totalChapters}
      />

      <CourseAnnouncements courseId={course.id} />

      <UpcomingEvents events={calendarEvents} />

      <ModuleList
        courseId={course.id}
        modules={sortedModules}
        completedChapterIds={completedChapterIds}
      />

      <div className="mt-6">
        <CertificateCard
          key={course.id}
          courseId={course.id}
          progress={enrollment.progress}
          certificate={certificate}
          onCertificateUpdate={onCertificateUpdate}
        />
      </div>

      <div className="flex items-center gap-2 mt-6">
        {materials.length > 0 && (
          <Button variant="outline" size="sm" onClick={() => setMaterialsModal(true)}>
            <Paperclip className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
            Materials ({materials.length})
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={() => setReviewsModal(true)}>
          <Star className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          Reviews
        </Button>
      </div>

      <MaterialsModal
        open={materialsModal}
        onClose={() => setMaterialsModal(false)}
        materials={materials}
        downloadingPath={downloadingPath}
        onDownload={handleDownload}
      />

      <Modal open={reviewsModal} onClose={() => setReviewsModal(false)} title="Course Reviews">
        <CourseReviews courseId={course.id} />
      </Modal>
    </div>
  )
}
