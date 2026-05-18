import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Megaphone } from "lucide-react"
import { EmptyState, Modal } from "@/components/patterns"
import type { Announcement } from "@/types"
import { AnnouncementPager } from "@/components/announcements/AnnouncementPager"

interface Props {
  open: boolean
  onClose: () => void
  announcements: Announcement[]
  title: string
  content: string
  onTitleChange: (next: string) => void
  onContentChange: (next: string) => void
  posting: boolean
  onPost: () => void
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
  posting,
  onPost,
  onDelete,
}: Props) {
  const { t } = useTranslation()
  return (
    <Modal open={open} onClose={onClose} title={t("teacherEditor.modals.announcements.title")}>
      <div className="space-y-4">
        <div className="space-y-3 border rounded-lg p-3 bg-muted/30">
          <Input
            value={title}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder={t("teacherEditor.modals.announcements.titlePlaceholder")}
          />
          <Textarea
            fieldSize="sm"
            value={content}
            onChange={(e) => onContentChange(e.target.value)}
            placeholder={t("teacherEditor.modals.announcements.contentPlaceholder")}
          />
          <Button size="sm" onClick={onPost} disabled={posting || !title.trim()}>
            <Megaphone className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
            {posting
              ? t("teacherEditor.modals.announcements.posting")
              : t("teacherEditor.modals.announcements.post")}
          </Button>
        </div>
        {announcements.length === 0 ? (
          <EmptyState
            variant="compact"
            icon={<Megaphone strokeWidth={1.75} aria-hidden />}
            title={t("teacherEditor.modals.announcements.empty")}
          />
        ) : (
          <AnnouncementPager announcements={announcements} onDelete={onDelete} />
        )}
      </div>
    </Modal>
  )
}
