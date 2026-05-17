import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Megaphone, Trash2 } from "lucide-react"
import { EmptyState, Modal } from "@/components/patterns"
import type { Announcement } from "@/types"
import { formatDateTime } from "@/i18n/format"

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
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {announcements.map((a) => (
              <div key={a.id} className="flex items-start gap-3 p-3 border rounded-lg">
                <Megaphone className="mt-0.5 h-4 w-4 shrink-0 text-info" strokeWidth={1.75} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-wrap-safe">{a.title}</p>
                  {a.content && (
                    <p className="mt-0.5 text-xs text-muted-foreground text-wrap-safe whitespace-pre-line">
                      {a.content}
                    </p>
                  )}
                  <time className="mt-1 block text-xs text-muted-foreground/60">
                    {formatDateTime(a.created_at)}
                  </time>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 text-destructive hover:text-destructive shrink-0"
                  onClick={() => onDelete(a.id)}
                  aria-label={t("teacherEditor.modals.announcements.deleteAria", { title: a.title })}
                >
                  <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}
