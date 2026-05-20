import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Paperclip, Star } from "lucide-react"
import { Button } from "@/components/ui/button"
import CourseAnnouncements from "@/components/announcements/CourseAnnouncements"
import CourseReviews from "@/components/course/CourseReviews"
import CertificateCard from "@/components/course/CertificateCard"
import CompletionDialog from "@/components/course/CompletionDialog"
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
  const { t } = useTranslation()
  const [materialsModal, setMaterialsModal] = useState(false)
  const [reviewsModal, setReviewsModal] = useState(false)
  const [downloadingPath, setDownloadingPath] = useState<string | null>(null)
  const [showCompletion, setShowCompletion] = useState(false)

  const enrolledCohort = cohorts.find((c) => c.id === enrollment.cohort_id)

  // Course-completion celebration: when a student lands on this view
  // with progress at 100% for the first time on this device, open the
  // celebration dialog. We guard with a per-user-per-course
  // localStorage flag — scoped by ``user_id`` so a second account on
  // a shared device still gets its own celebration moment for a
  // course the first user already finished. The flag is written on
  // close (not on open) so a closed-before-render edge case doesn't
  // silently swallow the moment.
  const celebrationFlagKey = `equip.celebrated.${enrollment.user_id}.${course.id}`

  useEffect(() => {
    if (!(enrollment.progress >= 100)) return
    if (typeof window === "undefined") return
    if (window.localStorage.getItem(celebrationFlagKey) === "1") return
    setShowCompletion(true)
  }, [enrollment.progress, celebrationFlagKey])

  const handleCloseCompletion = useCallback(() => {
    setShowCompletion(false)
    if (typeof window === "undefined") return
    try {
      window.localStorage.setItem(celebrationFlagKey, "1")
    } catch {
      // localStorage can be denied in some private-browsing contexts;
      // in that case the dialog will re-show on next visit. Acceptable.
    }
  }, [celebrationFlagKey])

  const handleDownload = useCallback(async (path: string) => {
    setDownloadingPath(path)
    try {
      const url = await storageService.getSignedMaterialUrl(path)
      window.open(url, "_blank", "noopener,noreferrer")
    } catch {
      toast({ title: t("courseDetail.downloadFailed"), variant: "destructive" })
    } finally {
      setDownloadingPath(null)
    }
  }, [t])

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
            {t("courseDetail.materialsButton", { count: materials.length })}
          </Button>
        )}
        <Button variant="outline" size="sm" onClick={() => setReviewsModal(true)}>
          <Star className="mr-1.5 h-4 w-4" strokeWidth={1.75} aria-hidden />
          {t("courseDetail.reviewsButton")}
        </Button>
      </div>

      <MaterialsModal
        open={materialsModal}
        onClose={() => setMaterialsModal(false)}
        materials={materials}
        downloadingPath={downloadingPath}
        onDownload={handleDownload}
      />

      <Modal open={reviewsModal} onClose={() => setReviewsModal(false)} title={t("courseDetail.reviewsModalTitle")}>
        <CourseReviews courseId={course.id} />
      </Modal>

      <CompletionDialog
        open={showCompletion}
        onClose={handleCloseCompletion}
        courseId={course.id}
        courseTitle={course.title}
        hasCertificate={certificate !== null}
        onCertificateRequested={onCertificateUpdate}
      />
    </div>
  )
}
