import type { Ref } from "react"
import { useTranslation } from "react-i18next"
import { UploadRightsNotice } from "@/components/legal/UploadRightsNotice"
import { Button } from "@/components/ui/button"
import { Download, Loader2, Paperclip, X } from "lucide-react"
import { EmptyState, Modal } from "@/components/patterns"
import type { MaterialFile } from "./types"
import { formatFileSize } from "@/lib/fileSize"
import { acceptAttribute, COURSE_MATERIALS } from "@/lib/uploadLimits"

interface Props {
  open: boolean
  onClose: () => void
  materials: MaterialFile[]
  uploading: boolean
  onUploadClick: () => void
  onUploadChange: (e: React.ChangeEvent<HTMLInputElement>) => void
  onDownload: (m: MaterialFile) => void
  onDelete: (m: MaterialFile) => void
  fileInputRef: Ref<HTMLInputElement>
}

// Exactly what the `course-materials` bucket accepts. The list this
// replaced offered ``.mp4`` — the bucket knows ``audio/mp4``, not video,
// so the picker promised something the server always refused (video in
// the product is a YouTube link) — and did not offer ``.m4a``, which is
// what an iPhone voice memo is.
const ACCEPTED_TYPES = acceptAttribute(COURSE_MATERIALS)

export function MaterialsModal({
  open,
  onClose,
  materials,
  uploading,
  onUploadClick,
  onUploadChange,
  onDownload,
  onDelete,
  fileInputRef,
}: Props) {
  const { t } = useTranslation()
  return (
    <Modal open={open} onClose={onClose} title={t("teacherEditor.modals.materials.title")} size="wide">
      <div className="space-y-4">
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={onUploadClick}
          disabled={uploading}
        >
          {uploading ? (
            <Loader2 className="h-4 w-4 mr-1.5 animate-spin" strokeWidth={1.75} />
          ) : (
            <Paperclip className="h-4 w-4 mr-1.5" strokeWidth={1.75} />
          )}
          {t("teacherEditor.modals.materials.upload")}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES}
          className="hidden"
          aria-label={t("teacherEditor.modals.materials.upload")}
          onChange={onUploadChange}
        />
        <UploadRightsNotice className="-mt-2" />
        {materials.length === 0 ? (
          <EmptyState
            variant="compact"
            icon={<Paperclip strokeWidth={1.75} aria-hidden />}
            title={t("teacherEditor.modals.materials.empty")}
          />
        ) : (
          // No inner scroller: the list used to be capped at 240px inside a
          // dialog that already scrolls at 85vh, so a course with four
          // attachments scrolled in a box inside a box — with the file names
          // truncated on top of that. The dialog's own cap is enough.
          <div className="space-y-2">
            {materials.map((m) => (
              <div
                key={m.path}
                className="flex items-center gap-3 rounded-md border p-3 transition-colors hover:bg-muted/40"
              >
                <Paperclip className="h-4 w-4 text-ink-muted shrink-0" strokeWidth={1.75} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm [overflow-wrap:anywhere]">{m.name}</p>
                  {m.size && (
                    <p className="text-xs text-ink-muted">{formatFileSize(m.size, t, "teacherEditor.modals.materials")}</p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 shrink-0"
                  onClick={() => onDownload(m)}
                  aria-label={t("teacherEditor.modals.materials.downloadAria", { name: m.name })}
                >
                  <Download className="h-3.5 w-3.5" strokeWidth={1.75} />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 text-destructive hover:text-destructive shrink-0"
                  onClick={() => onDelete(m)}
                  aria-label={t("teacherEditor.modals.materials.deleteAria", { name: m.name })}
                >
                  <X className="h-3.5 w-3.5" strokeWidth={1.75} />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}
