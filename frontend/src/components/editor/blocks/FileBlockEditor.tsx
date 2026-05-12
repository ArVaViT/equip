import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { FileText, Loader2, Paperclip, Upload, X } from "lucide-react"
import { coursesService } from "@/services/courses"
import { storageService } from "@/services/storage"
import { getErrorDetail } from "@/lib/errorDetail"
import { toast } from "@/lib/toast"
import type { ChapterBlock } from "@/types"

interface Props {
  block: ChapterBlock
  chapterId: string
  onUpdated: (updated: ChapterBlock) => void
}

/**
 * File-attachment editor for a chapter block: upload/replace/remove a
 * single file. Owns its own "uploading" state so sibling blocks aren't
 * affected by this block's upload.
 */
export function FileBlockEditor({ block, chapterId, onUpdated }: Props) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const hasFile = Boolean(block.file_bucket && block.file_path)

  const upload = async (file: File) => {
    setUploading(true)
    try {
      const { bucket, path, name } = await storageService.uploadBlockFile(chapterId, file)
      const updated = await coursesService.updateBlock(block.id, {
        file_bucket: bucket,
        file_path: path,
        file_name: name,
      })
      onUpdated(updated)
      toast({ title: t("blockEditor.file.uploaded"), variant: "success" })
    } catch (error: unknown) {
      const detail = getErrorDetail(error) || t("blockEditor.file.uploadFailedDefault")
      toast({ title: detail, variant: "destructive" })
    } finally {
      setUploading(false)
    }
  }

  const clear = async () => {
    try {
      const updated = await coursesService.updateBlock(block.id, {
        file_bucket: null,
        file_path: null,
        file_name: null,
      })
      onUpdated(updated)
    } catch {
      toast({ title: t("blockEditor.file.removeFailed"), variant: "destructive" })
    }
  }

  return (
    <div className="space-y-2">
      <Label className="text-xs flex items-center gap-1.5">
        <Paperclip className="h-3.5 w-3.5" />
        {t("blockEditor.file.attachedFile")}
      </Label>
      {hasFile ? (
        <div className="flex items-center gap-2 rounded-md border px-3 py-2 bg-muted/30">
          <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
          <span className="text-sm flex-1 truncate">
            {block.file_name ?? block.file_path}
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="h-7 text-xs"
          >
            {uploading ? <Loader2 className="h-3 w-3 animate-spin" /> : t("blockEditor.file.replace")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={clear}
            disabled={uploading}
            className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
            aria-label={t("blockEditor.file.removeAria")}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      ) : (
        <Button
          size="sm"
          variant="outline"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="w-full border-dashed"
        >
          {uploading ? (
            <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
          ) : (
            <Upload className="h-3.5 w-3.5 mr-1.5" />
          )}
          {uploading ? t("blockEditor.file.uploading") : t("blockEditor.file.uploadCta")}
        </Button>
      )}
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) void upload(file)
          e.target.value = ""
        }}
      />
    </div>
  )
}
