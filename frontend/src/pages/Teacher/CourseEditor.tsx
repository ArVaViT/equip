import { useCallback, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { useConfirm } from "@/components/ui/alert-dialog"
import {
  Calendar,
  CalendarDays,
  Eye,
  EyeOff,
  Lock,
  Megaphone,
  MoreHorizontal,
  Paperclip,
} from "lucide-react"
import { useAuth } from "@/context/useAuth"
import { ROLES } from "@/types"
import {
  ErrorState,
  InlineEdit,
  InlineEditCover,
  PageHeader,
} from "@/components/patterns"
import { useUserTour } from "@/hooks/useUserTour"
import { courseEditorSteps } from "@/lib/tourSteps"
import {
  AccessModeModal,
  AnnouncementsModal,
  CourseEditorSkeleton,
  CourseReadinessCard,
  EnrollmentModal,
  EventsModal,
  MaterialsModal,
  ModulesList,
  useAnnouncementsSection,
  useCourseData,
  useCourseReadiness,
  useEventsSection,
  useMaterialsSection,
} from "./editor"
import type { CourseEditorModal } from "./editor/types"
import type { ReadinessAction } from "@/services/courseReadiness"

/**
 * Course editor: the one place teachers edit everything about a course.
 *
 * This component is deliberately thin. Every concern (course basics,
 * announcements, materials, cohorts, events) is owned by a dedicated hook
 * from `./editor/`; this file just wires those hooks up to their modal
 * components and manages which modal is currently open.
 */
export default function CourseEditor() {
  const { courseId } = useParams<{ courseId: string }>()
  const navigate = useNavigate()
  const confirm = useConfirm()
  const { t } = useTranslation()
  const { user } = useAuth()
  const isAdmin = user?.role === ROLES.ADMIN

  const [modal, setModal] = useState<CourseEditorModal>(null)
  const [savingAccessMode, setSavingAccessMode] = useState(false)
  const closeModal = useCallback(() => setModal(null), [])
  const goBack = useCallback(() => navigate("/teacher"), [navigate])

  const data = useCourseData(courseId, confirm, goBack)
  const announcements = useAnnouncementsSection(courseId, confirm)
  const materials = useMaterialsSection(courseId, confirm)
  // Cohort management lives in the admin UI per ADR-010 — teachers
  // don't create or manage cohorts. Their only cohort surface is the
  // gradebook filter for their course.
  const events = useEventsSection(courseId, confirm)
  const readiness = useCourseReadiness(courseId)
  const descriptionAnchorRef = useRef<HTMLDivElement | null>(null)
  const coverAnchorRef = useRef<HTMLDivElement | null>(null)
  useUserTour({
    tourId: "course-editor-v1",
    steps: courseEditorSteps(t),
    ready: !data.loading && data.course !== null,
  })

  const pub = data.course?.status === "published"

  // ── Publish-flow with critical-readiness confirm ────────────────
  // When the teacher tries to publish a course that has critical
  // readiness failures, we warn instead of blocking. They can still
  // proceed (no hard gate) but they have to make a deliberate choice.
  const handleTogglePublish = useCallback(async () => {
    if (!pub && readiness.report && readiness.report.critical_failing > 0) {
      const failing = readiness.report.checks
        .filter((c) => c.severity === "critical" && !c.passed)
        .map((c) =>
          t(c.message_key, {
            defaultValue: c.message_key,
            title: c.subject?.title,
          }),
        )
      const ok = await confirm({
        title: t("courseReadiness.publishConfirm.title"),
        description: t("courseReadiness.publishConfirm.description", {
          count: readiness.report.critical_failing,
        }),
        // Show up to 5 specific issues inline so the teacher knows what
        // they're shipping; one-line, comma-joined feels truthful without
        // a wall of bullet points.
        bulletList: failing.slice(0, 5),
        confirmLabel: t("courseReadiness.publishConfirm.confirm"),
        tone: "destructive",
      })
      if (!ok) return
    }
    await data.togglePublish()
    void readiness.refresh()
  }, [confirm, data, pub, readiness, t])

  // ── Deep-link fix actions ───────────────────────────────────────
  const handleFix = useCallback(
    (action: ReadinessAction) => {
      const params = action.params
      switch (action.type) {
        case "set_description": {
          descriptionAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
          const editButton =
            descriptionAnchorRef.current?.querySelector<HTMLButtonElement>("button")
          editButton?.click()
          break
        }
        case "set_cover_image": {
          coverAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })
          break
        }
        case "open_enrollment":
          setModal("enroll")
          break
        case "add_module":
          void data.addModule().then(() => void readiness.refresh())
          break
        case "open_module":
          if (params.module_id)
            navigate(`/teacher/courses/${courseId}/modules/${params.module_id}/edit`)
          break
        case "open_chapter":
        case "open_quiz":
        case "open_assignment":
          if (params.module_id && params.chapter_id)
            navigate(
              `/teacher/courses/${courseId}/modules/${params.module_id}/chapters/${params.chapter_id}/edit`,
            )
          break
        case "open_grading_weights":
          navigate(`/teacher/courses/${courseId}/gradebook`)
          break
      }
    },
    [courseId, data, navigate, readiness],
  )

  if (data.loading) return <CourseEditorSkeleton />
  if (!data.course)
    return (
      <div className="container mx-auto px-4">
        <ErrorState
          title={t("courseEditor.notFound.title")}
          description={t("courseEditor.notFound.description")}
          action={
            <Button variant="outline" size="sm" onClick={goBack}>
              {t("courseEditor.notFound.backToCourses")}
            </Button>
          }
        />
      </div>
    )

  const { course } = data

  return (
    <div className="container mx-auto max-w-4xl px-4 py-6 sm:py-8">
      <div data-tour="course-editor-header">
      <PageHeader
        backTo="/teacher"
        backLabel={t("courseEditor.myCourses")}
        cover={
          <div ref={coverAnchorRef}>
            <InlineEditCover
              value={course.image_url}
              onUpload={data.uploadCover}
              onRemove={data.removeCover}
              alt={course.title}
            />
          </div>
        }
        title={
          <InlineEdit
            size="h1"
            value={course.title}
            onSave={(v) => data.savePatch({ title: v })}
            required
            placeholder={t("courseEditor.untitledCourse")}
            ariaLabel={t("courseEditor.editTitle")}
            maxLength={200}
          />
        }
        description={
          <div ref={descriptionAnchorRef}>
            <InlineEdit
              size="body"
              multiline
              value={course.description ?? ""}
              onSave={(v) => data.savePatch({ description: v || null })}
              placeholder={t("courseEditor.addDescription")}
              ariaLabel={t("courseEditor.editDescription")}
              maxLength={2000}
            />
          </div>
        }
        meta={
          <Badge variant={pub ? "success" : "warning"} className="uppercase tracking-wide">
            {pub ? t("courseEditor.published") : t("courseEditor.draft")}
          </Badge>
        }
        actions={
          <>
            <Button variant="outline" size="sm" onClick={handleTogglePublish}>
              {pub ? (
                <EyeOff className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
              ) : (
                <Eye className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
              )}
              {pub ? t("courseEditor.unpublish") : t("courseEditor.publish")}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button data-tour="course-editor-tabs" variant="outline" size="sm" aria-label={t("courseEditor.moreActions")}>
                  <MoreHorizontal className="h-4 w-4" strokeWidth={1.75} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setModal("enroll")}>
                  <Calendar strokeWidth={1.75} /> {t("courseEditor.menu.enrollment")}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setModal("announce")}>
                  <Megaphone strokeWidth={1.75} /> {t("courseEditor.menu.announcements")}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setModal("materials")}>
                  <Paperclip strokeWidth={1.75} /> {t("courseEditor.menu.materials")}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => {
                    events.resetForm()
                    setModal("events")
                  }}
                >
                  <CalendarDays strokeWidth={1.75} /> {t("courseEditor.menu.events")}
                </DropdownMenuItem>
                {isAdmin && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => setModal("access")}>
                      <Lock strokeWidth={1.75} /> {t("courseEditor.menu.accessMode")}
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />
      </div>

      <CourseReadinessCard
        report={readiness.report}
        loading={readiness.loading}
        onFix={handleFix}
      />

      <div data-tour="course-editor-modules">
      <ModulesList
        courseId={courseId ?? ""}
        modules={data.sortedModules}
        onDragEnd={data.reorderModules}
        onAdd={async () => {
          await data.addModule()
          void readiness.refresh()
        }}
        onRemove={async (id) => {
          await data.removeModule(id)
          void readiness.refresh()
        }}
      />
      </div>

      <EnrollmentModal
        open={modal === "enroll"}
        onClose={closeModal}
        start={data.enrollStart}
        end={data.enrollEnd}
        onStartChange={data.setEnrollStart}
        onEndChange={data.setEnrollEnd}
        saving={data.savingEnrollment}
        onSave={async () => {
          if (await data.saveEnrollment()) closeModal()
        }}
      />

      <AnnouncementsModal
        open={modal === "announce"}
        onClose={() => {
          closeModal()
          announcements.resetForm()
        }}
        announcements={announcements.announcements}
        title={announcements.title}
        content={announcements.content}
        onTitleChange={announcements.setTitle}
        onContentChange={announcements.setContent}
        posting={announcements.posting}
        onPost={announcements.post}
        onDelete={announcements.remove}
      />

      <MaterialsModal
        open={modal === "materials"}
        onClose={closeModal}
        materials={materials.materials}
        uploading={materials.uploading}
        onUploadClick={materials.triggerUpload}
        onUploadChange={materials.handleUpload}
        onDownload={materials.download}
        onDelete={materials.remove}
        fileInputRef={materials.inputRef}
      />

      <EventsModal
        open={modal === "events"}
        onClose={() => {
          closeModal()
          events.resetForm()
        }}
        events={events.events}
        form={events.form}
        onFormChange={events.setForm}
        editingId={events.editingId}
        saving={events.saving}
        onSave={events.save}
        onCancelEdit={events.resetForm}
        onEdit={events.startEdit}
        onDelete={events.remove}
      />

      {isAdmin && (
        <AccessModeModal
          open={modal === "access"}
          onClose={closeModal}
          current={course.access_mode}
          saving={savingAccessMode}
          onSave={async (next) => {
            setSavingAccessMode(true)
            try {
              await data.savePatch({ access_mode: next })
              closeModal()
            } finally {
              setSavingAccessMode(false)
            }
          }}
        />
      )}
    </div>
  )
}
