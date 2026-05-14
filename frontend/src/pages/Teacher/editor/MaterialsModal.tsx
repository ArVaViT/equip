import type { Ref } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Download, Loader2, Paperclip, X } from "lucide-react"
import { Modal } from "@/components/patterns"
import type { MaterialFile } from "./types"

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

const ACCEPTED_TYPES = ".pdf,.doc,.docx,.ppt,.pptx,.txt,.mp3,.wav,.ogg,.mp4"

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
    <Modal open={open} onClose={onClose} title={t("teacherEditor.modals.materials.title")}>
      <div className="space-y-4">
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={onUploadClick}
          disabled={uploading}
        >
          {uploading ? (
            <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
          ) : (
            <Paperclip className="h-4 w-4 mr-1.5" />
          )}
          {t("teacherEditor.modals.materials.upload")}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES}
          className="hidden"
          onChange={onUploadChange}
        />
        {materials.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">
            {t("teacherEditor.modals.materials.empty")}
          </p>
        ) : (
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {materials.map((m) => (
              <div
                key={m.path}
                className="flex items-center gap-3 p-3 border rounded-lg hover:bg-muted/50 transition-colors"
              >
                <Paperclip className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-sm flex-1 truncate">{m.name}</span>
                {m.size && (
                  <span className="text-xs text-muted-foreground shrink-0">
                    {t("teacherEditor.modals.materials.sizeKb", { kb: (m.size / 1024).toFixed(0) })}
                  </span>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 shrink-0"
                  onClick={() => onDownload(m)}
                  aria-label={t("teacherEditor.modals.materials.downloadAria", { name: m.name })}
                >
                  <Download className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 text-destructive hover:text-destructive shrink-0"
                  onClick={() => onDelete(m)}
                  aria-label={t("teacherEditor.modals.materials.deleteAria", { name: m.name })}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}
