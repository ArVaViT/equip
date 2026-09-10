import { useCallback, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { FileText, Loader2, Paperclip, Upload, X } from "lucide-react"
import { coursesService } from "@/services/courses"
import { storageService } from "@/services/storage"
import { toast } from "@/lib/toast"
import { describeUploadError, preflightUpload } from "@/lib/uploadError"
import { acceptAttribute, COURSE_MATERIALS } from "@/lib/uploadLimits"
import type { ChapterBlock } from "@/types"

interface Props {
  block: ChapterBlock
  courseId: string
  chapterId: string
  onUpdated: (updated: ChapterBlock) => void
}

/**
 * File-attachment editor for a chapter block: upload/replace/remove a
 * single file. Owns its own "uploading" state so sibling blocks aren't
 * affected by this block's upload.
 */
export function FileBlockEditor({ block, courseId, chapterId, onUpdated }: Props) {
  const { t } = useTranslation()
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [opening, setOpening] = useState(false)
  const hasFile = Boolean(block.file_bucket && block.file_path)

  const upload = async (file: File) => {
    // Refuse what the bucket would refuse, in the teacher's language and
    // before the bytes leave the browser.
    const issue = preflightUpload(file, COURSE_MATERIALS)
    if (issue) {
      toast({ title: t("blockEditor.file.uploadFailedDefault"), description: issue.message, variant: "destructive" })
      return
    }
    setUploading(true)
    try {
      const { bucket, path, name } = await storageService.uploadBlockFile(courseId, chapterId, file)
      const updated = await coursesService.updateBlock(block.id, {
        file_bucket: bucket,
        file_path: path,
        file_name: name,
      })
      onUpdated(updated)
      toast({ title: t("blockEditor.file.uploaded"), variant: "success" })
    } catch (error: unknown) {
      toast({
        title: t("blockEditor.file.uploadFailedDefault"),
        description: describeUploadError(error, COURSE_MATERIALS),
        variant: "destructive",
      })
    } finally {
      setUploading(false)
    }
  }

  /**
   * Open the attached file, signing the URL at click time — the same
   * thing the student's chapter page does, and for the same reason: a
   * stored signature would outlive a JWT rotation.
   *
   * The teacher had no way to do this at all. The file name sat in a
   * `<span>`, so the obvious click — on the name of the file you just
   * uploaded, to check it is the right one — did nothing. Datadog counted
   * four dead clicks on `Lesson_1__9-12-26.pdf` from the teacher who
   * uploaded it, on 2026-09-07 and -08.
   */
  const open = useCallback(async () => {
    if (!block.file_bucket || !block.file_path || opening) return
    setOpening(true)
    try {
      const url = await storageService.getSignedBlockFileUrl(block.file_bucket, block.file_path)
      window.open(url, "_blank", "noopener,noreferrer")
    } catch {
      toast({ title: t("toast.openFileFailed"), variant: "destructive" })
    } finally {
      setOpening(false)
    }
  }, [block.file_bucket, block.file_path, opening, t])

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
        <Paperclip className="h-3.5 w-3.5" strokeWidth={1.75} />
        {t("blockEditor.file.attachedFile")}
      </Label>
      {hasFile ? (
        <div className="flex items-center gap-2 rounded-md border px-3 py-2 bg-muted/30">
          {opening ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin text-ink-muted" strokeWidth={1.75} aria-hidden />
          ) : (
            <FileText className="h-4 w-4 text-ink-muted shrink-0" strokeWidth={1.75} aria-hidden />
          )}
          <button
            type="button"
            onClick={() => void open()}
            disabled={opening}
            className="flex-1 truncate rounded-sm text-left text-sm underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:opacity-60"
            aria-label={t("blockEditor.file.openAria", {
              name: block.file_name ?? block.file_path,
            })}
          >
            {block.file_name ?? block.file_path}
          </button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => inputRef.current?.click()}
            disabled={uploading}
            className="h-7 text-xs"
          >
            {uploading ? <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.75} /> : t("blockEditor.file.replace")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={clear}
            disabled={uploading}
            className="h-7 w-7 p-0 text-ink-muted hover:text-destructive"
            aria-label={t("blockEditor.file.removeAria")}
          >
            <X className="h-3.5 w-3.5" strokeWidth={1.75} />
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
            <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" strokeWidth={1.75} />
          ) : (
            <Upload className="h-3.5 w-3.5 mr-1.5" strokeWidth={1.75} />
          )}
          {uploading ? t("blockEditor.file.uploading") : t("blockEditor.file.uploadCta")}
        </Button>
      )}
      <input
        ref={inputRef}
        type="file"
        accept={acceptAttribute(COURSE_MATERIALS)}
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
