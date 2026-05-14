import { useCallback, useState } from "react"
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
import {
  ErrorState,
  InlineEdit,
  InlineEditCover,
  PageHeader,
} from "@/components/patterns"
import {
  AccessModeModal,
  AnnouncementsModal,
  CourseEditorSkeleton,
  EnrollmentModal,
  EventsModal,
  MaterialsModal,
  ModulesList,
  useAnnouncementsSection,
  useCourseData,
  useEventsSection,
  useMaterialsSection,
} from "./editor"
import type { CourseEditorModal } from "./editor/types"

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
  const isAdmin = user?.role === "admin"

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

  const { course, published: pub } = data

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      <PageHeader
        backTo="/teacher"
        backLabel={t("courseEditor.myCourses")}
        cover={
          <InlineEditCover
            value={course.image_url}
            onUpload={data.uploadCover}
            onRemove={data.removeCover}
            alt={course.title}
          />
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
          <InlineEdit
            size="body"
            multiline
            value={course.description ?? ""}
            onSave={(v) => data.savePatch({ description: v || null })}
            placeholder={t("courseEditor.addDescription")}
            ariaLabel={t("courseEditor.editDescription")}
            maxLength={2000}
          />
        }
        meta={
          <Badge variant={pub ? "success" : "warning"} className="uppercase tracking-wide">
            {pub ? t("courseEditor.published") : t("courseEditor.draft")}
          </Badge>
        }
        actions={
          <>
            <Button variant="outline" size="sm" onClick={data.togglePublish}>
              {pub ? (
                <EyeOff className="h-3.5 w-3.5 mr-1.5" />
              ) : (
                <Eye className="h-3.5 w-3.5 mr-1.5" />
              )}
              {pub ? t("courseEditor.unpublish") : t("courseEditor.publish")}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" size="sm" aria-label={t("courseEditor.moreActions")}>
                  <MoreHorizontal className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setModal("enroll")}>
                  <Calendar /> {t("courseEditor.menu.enrollment")}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setModal("announce")}>
                  <Megaphone /> {t("courseEditor.menu.announcements")}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setModal("materials")}>
                  <Paperclip /> {t("courseEditor.menu.materials")}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => {
                    events.resetForm()
                    setModal("events")
                  }}
                >
                  <CalendarDays /> {t("courseEditor.menu.events")}
                </DropdownMenuItem>
                {isAdmin && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onSelect={() => setModal("access")}>
                      <Lock /> {t("courseEditor.menu.accessMode")}
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </>
        }
      />

      <ModulesList
        courseId={courseId ?? ""}
        modules={data.sortedModules}
        onDragEnd={data.reorderModules}
        onAdd={data.addModule}
        onRemove={data.removeModule}
      />

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
