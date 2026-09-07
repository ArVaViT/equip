import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Megaphone, Save } from "lucide-react"
import { EmptyState, Modal } from "@/components/patterns"
import type { Announcement } from "@/types"
import { AnnouncementPager } from "@/components/announcements/AnnouncementPager"

/** Mirrors ``AnnouncementCreate`` on the server (``max_length``). */
const TITLE_MAX = 200
const CONTENT_MAX = 5000

interface Props {
  open: boolean
  onClose: () => void
  announcements: Announcement[]
  title: string
  content: string
  onTitleChange: (next: string) => void
  onContentChange: (next: string) => void
  editingId: string | null
  posting: boolean
  onPost: () => void
  onEdit: (a: Announcement) => void
  onCancelEdit: () => void
  onDelete: (id: string) => void
}

export function AnnouncementsModal({
  open,
  onClose,
  announcements,
  title,
  content,
  onTitleChange,
  onContentChange,
  editingId,
  posting,
  onPost,
  onEdit,
  onCancelEdit,
  onDelete,
}: Props) {
  const { t } = useTranslation()
  return (
    <Modal open={open} onClose={onClose} title={t("teacherEditor.modals.announcements.title")}>
      <div className="space-y-4">
        <div className="space-y-3 rounded-md border bg-muted/30 p-3">
          <p className="text-xs font-medium text-ink-muted uppercase tracking-wide">
            {editingId
              ? t("teacherEditor.modals.announcements.editAnnouncement")
              : t("teacherEditor.modals.announcements.newAnnouncement")}
          </p>
          <Input
            value={title}
            maxLength={TITLE_MAX}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder={t("teacherEditor.modals.announcements.titlePlaceholder")}
          />
          <Textarea
            fieldSize="sm"
            value={content}
            maxLength={CONTENT_MAX}
            onChange={(e) => onContentChange(e.target.value)}
            placeholder={t("teacherEditor.modals.announcements.contentPlaceholder")}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={onPost} disabled={posting || !title.trim()}>
              {editingId ? (
                <Save className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
              ) : (
                <Megaphone className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
              )}
              {posting
                ? t(
                    editingId
                      ? "teacherEditor.modals.announcements.saving"
                      : "teacherEditor.modals.announcements.posting",
                  )
                : t(
                    editingId
                      ? "teacherEditor.modals.announcements.save"
                      : "teacherEditor.modals.announcements.post",
                  )}
            </Button>
            {editingId && (
              <Button size="sm" variant="ghost" onClick={onCancelEdit}>
                {t("teacherEditor.modals.announcements.cancel")}
              </Button>
            )}
            {!editingId && (
              <p className="text-xs text-ink-muted">
                {t("teacherEditor.modals.announcements.notifyHint")}
              </p>
            )}
          </div>
        </div>
        {announcements.length === 0 ? (
          <EmptyState
            variant="compact"
            icon={<Megaphone strokeWidth={1.75} aria-hidden />}
            title={t("teacherEditor.modals.announcements.empty")}
          />
        ) : (
          <AnnouncementPager announcements={announcements} onEdit={onEdit} onDelete={onDelete} />
        )}
      </div>
    </Modal>
  )
}
