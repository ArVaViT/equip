import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { storageService } from "@/services/storage"
import { toast } from "@/lib/toast"
import { describeUploadError, preflightUpload } from "@/lib/uploadError"
import { COURSE_MATERIALS } from "@/lib/uploadLimits"
import type { useConfirm } from "@/components/ui/alert-dialog"
import type { MaterialFile } from "./types"

type Confirm = ReturnType<typeof useConfirm>

interface MaterialsSection {
  materials: MaterialFile[]
  uploading: boolean
  inputRef: React.RefObject<HTMLInputElement>
  triggerUpload: () => void
  handleUpload: (e: React.ChangeEvent<HTMLInputElement>) => Promise<void>
  download: (m: MaterialFile) => Promise<void>
  remove: (m: MaterialFile) => Promise<void>
}

/**
 * Owns the "Materials" modal state for a course: list, upload input ref,
 * and upload/download/delete handlers.
 */
export function useMaterialsSection(
  courseId: string | undefined,
  confirm: Confirm,
): MaterialsSection {
  const { t } = useTranslation()
  const [materials, setMaterials] = useState<MaterialFile[]>([])
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!courseId) return
    let cancelled = false
    storageService
      .listCourseMaterials(courseId)
      .then((m) => {
        if (!cancelled) setMaterials(m)
      })
      .catch(() => {
        if (!cancelled) setMaterials([])
      })
    return () => {
      cancelled = true
    }
  }, [courseId])

  const triggerUpload = useCallback(() => {
    inputRef.current?.click()
  }, [])

  const handleUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file || !courseId) return
      // What the bucket would refuse, said here first and in the
      // teacher's language; a 60 MB recording should not upload for a
      // minute to be turned away.
      const issue = preflightUpload(file, COURSE_MATERIALS)
      if (issue) {
        toast({
          title: t("teacherEditor.toast.materialUploadFailed"),
          description: issue.message,
          variant: "destructive",
        })
        if (inputRef.current) inputRef.current.value = ""
        return
      }
      setUploading(true)
      try {
        await storageService.uploadCourseMaterial(courseId, file)
        setMaterials(await storageService.listCourseMaterials(courseId))
      } catch (error: unknown) {
        // This used to be a bare `catch {}` — Storage's reason was thrown
        // away and every failure read "Загрузка не удалась".
        toast({
          title: t("teacherEditor.toast.materialUploadFailed"),
          description: describeUploadError(error, COURSE_MATERIALS),
          variant: "destructive",
        })
      } finally {
        setUploading(false)
        if (inputRef.current) inputRef.current.value = ""
      }
    },
    [courseId, t],
  )

  const download = useCallback(
    async (m: MaterialFile) => {
      try {
        window.open(
          await storageService.getSignedMaterialUrl(m.path),
          "_blank",
          "noopener,noreferrer",
        )
      } catch {
        toast({ title: t("teacherEditor.toast.materialDownloadFailed"), variant: "destructive" })
      }
    },
    [t],
  )

  const remove = useCallback(
    async (m: MaterialFile) => {
      const ok = await confirm({
        title: t("teacherEditor.confirm.deleteMaterialTitle"),
        description: t("teacherEditor.confirm.deleteMaterialDescription", { name: m.name }),
        confirmLabel: t("teacherEditor.confirm.deleteMaterialAction"),
        tone: "destructive",
      })
      if (!ok) return
      try {
        await storageService.deleteCourseMaterial(m.path)
        setMaterials((p) => p.filter((x) => x.path !== m.path))
      } catch {
        toast({ title: t("teacherEditor.toast.materialDeleteFailed"), variant: "destructive" })
      }
    },
    [confirm, t],
  )

  return {
    materials,
    uploading,
    inputRef,
    triggerUpload,
    handleUpload,
    download,
    remove,
  }
}
