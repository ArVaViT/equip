import * as React from "react"
import { useTranslation } from "react-i18next"
import { ImagePlus, Loader2, Trash2, Upload } from "lucide-react"
import { cn } from "@/lib/utils"
import { toProxyImage } from "@/lib/images"
import { toast } from "@/lib/toast"
import { useConfirm } from "@/components/ui/alert-dialog"

interface InlineEditCoverProps {
  value: string | null | undefined
  onUpload: (file: File) => Promise<string>
  onRemove?: () => Promise<void> | void
  alt: string
  aspect?: "16/9" | "4/3" | "21/9" | "1/1"
  disabled?: boolean
  className?: string
  maxSizeMB?: number
}

const aspectClasses: Record<NonNullable<InlineEditCoverProps["aspect"]>, string> = {
  "16/9": "aspect-[16/9]",
  "4/3": "aspect-[4/3]",
  "21/9": "aspect-[21/9]",
  "1/1": "aspect-square",
}

export function InlineEditCover({
  value,
  onUpload,
  onRemove,
  alt,
  aspect = "16/9",
  disabled = false,
  className,
  maxSizeMB = 8,
}: InlineEditCoverProps) {
  const confirm = useConfirm()
  const { t } = useTranslation()
  const inputRef = React.useRef<HTMLInputElement>(null)
  const [busy, setBusy] = React.useState(false)
  const [dragOver, setDragOver] = React.useState(false)

  const handleFile = async (file: File | undefined | null) => {
    if (!file) return
    if (!file.type.startsWith("image/")) {
      toast({ title: "Unsupported file", description: "Pick an image file.", variant: "destructive" })
      return
    }
    if (file.size > maxSizeMB * 1024 * 1024) {
      toast({
        title: "Image too large",
        description: `Max ${maxSizeMB} MB.`,
        variant: "destructive",
      })
      return
    }
    try {
      setBusy(true)
      await onUpload(file)
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Upload failed"
      toast({ title: "Upload failed", description: msg, variant: "destructive" })
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!onRemove) return
    const ok = await confirm({
      title: "Remove cover?",
      description: "This will clear the course cover image.",
      tone: "destructive",
      confirmLabel: "Remove",
    })
    if (!ok) return
    try {
      setBusy(true)
      await onRemove()
    } finally {
      setBusy(false)
    }
  }

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    if (disabled) return
    void handleFile(e.dataTransfer.files?.[0])
  }

  const empty = !value

  return (
    <div
      className={cn(
        "relative w-full overflow-hidden rounded-lg border border-border bg-muted",
        aspectClasses[aspect],
        dragOver && "ring-2 ring-ring ring-offset-2",
        className,
      )}
      onDragOver={(e) => {
        if (disabled) return
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      {empty ? (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled || busy}
          className="group flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {busy ? (
            <Loader2 className="h-6 w-6 animate-spin" />
          ) : (
            <>
              <ImagePlus className="h-6 w-6" />
              <span className="text-sm">
                {disabled ? "No cover" : "Click or drop image"}
              </span>
            </>
          )}
        </button>
      ) : (
        <>
          <img
            src={toProxyImage(value)}
            alt={alt}
            className="h-full w-full object-cover"
            loading="lazy"
            decoding="async"
          />
          {!disabled && (
            <div className="absolute inset-0 flex items-end justify-end gap-2 bg-gradient-to-t from-black/50 via-black/0 to-transparent p-3 opacity-0 transition-opacity hover:opacity-100 focus-within:opacity-100">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                disabled={busy}
                className="inline-flex items-center gap-1.5 rounded-md bg-background/90 px-2.5 py-1 text-xs font-medium text-foreground shadow-sm ring-1 ring-border hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {busy ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Upload className="h-3.5 w-3.5" />
                )}
                {t("inlineEdit.cover.replace")}
              </button>
              {onRemove && (
                <button
                  type="button"
                  onClick={remove}
                  disabled={busy}
                  className="inline-flex items-center gap-1.5 rounded-md bg-background/90 px-2.5 py-1 text-xs font-medium text-foreground shadow-sm ring-1 ring-border hover:bg-destructive hover:text-destructive-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {t("inlineEdit.cover.remove")}
                </button>
              )}
            </div>
          )}
        </>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          e.target.value = ""
          void handleFile(f)
        }}
      />
    </div>
  )
}
