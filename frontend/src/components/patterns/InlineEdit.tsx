import * as React from "react"
import { useTranslation } from "react-i18next"
import { Check, Pencil, X, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

type Size = "h1" | "h2" | "body"

interface InlineEditProps {
  value: string
  onSave: (next: string) => Promise<void> | void
  placeholder?: string
  size?: Size
  multiline?: boolean
  maxLength?: number
  disabled?: boolean
  required?: boolean
  className?: string
  textClassName?: string
  ariaLabel?: string
}

const sizeClasses: Record<Size, string> = {
  h1: "font-serif text-3xl md:text-4xl font-semibold leading-tight tracking-tight",
  h2: "font-serif text-xl md:text-2xl font-semibold leading-tight",
  body: "text-sm leading-relaxed",
}

export function InlineEdit({
  value,
  onSave,
  placeholder,
  size = "body",
  multiline = false,
  maxLength,
  disabled = false,
  required = false,
  className,
  textClassName,
  ariaLabel,
}: InlineEditProps) {
  const { t } = useTranslation()
  const resolvedPlaceholder = placeholder ?? t("inlineEdit.defaultPlaceholder")
  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft] = React.useState(value)
  const [saving, setSaving] = React.useState(false)
  const inputRef = React.useRef<HTMLTextAreaElement | HTMLInputElement>(null)

  React.useEffect(() => {
    if (!editing) setDraft(value)
  }, [value, editing])

  React.useEffect(() => {
    if (!editing) return
    const el = inputRef.current
    if (!el) return
    el.focus()
    if ("setSelectionRange" in el) {
      try {
        el.setSelectionRange(el.value.length, el.value.length)
      } catch {
        // ignore
      }
    }
    if (multiline && el instanceof HTMLTextAreaElement) {
      el.style.height = "auto"
      el.style.height = `${el.scrollHeight}px`
    }
  }, [editing, multiline])

  const start = () => {
    if (disabled) return
    setDraft(value)
    setEditing(true)
  }

  const cancel = () => {
    setDraft(value)
    setEditing(false)
  }

  const commit = async () => {
    const trimmed = draft.trim()
    if (required && !trimmed) {
      cancel()
      return
    }
    if (trimmed === value.trim()) {
      setEditing(false)
      return
    }
    try {
      setSaving(true)
      await onSave(trimmed)
      setEditing(false)
    } finally {
      setSaving(false)
    }
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (e.key === "Escape") {
      e.preventDefault()
      cancel()
      return
    }
    if (e.key === "Enter") {
      if (multiline && !(e.metaKey || e.ctrlKey)) return
      e.preventDefault()
      void commit()
    }
  }

  const onBlur = () => {
    if (!saving) void commit()
  }

  const resize = (el: HTMLTextAreaElement) => {
    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`
  }

  if (editing) {
    const sharedProps = {
      value: draft,
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
        setDraft(e.target.value)
        if (multiline && e.currentTarget instanceof HTMLTextAreaElement) {
          resize(e.currentTarget)
        }
      },
      onKeyDown,
      onBlur,
      maxLength,
      placeholder: resolvedPlaceholder,
      disabled: saving,
      "aria-label": ariaLabel,
      className: cn(
        "w-full rounded-md border border-input bg-background px-2 py-1 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        sizeClasses[size],
        textClassName,
      ),
    }

    return (
      <span className={cn("inline-flex w-full items-start gap-2", className)}>
        {multiline ? (
          <textarea
            {...sharedProps}
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            rows={2}
          />
        ) : (
          <input
            {...sharedProps}
            ref={inputRef as React.RefObject<HTMLInputElement>}
            type="text"
          />
        )}
        <span className="flex shrink-0 items-center gap-1 pt-1">
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" strokeWidth={1.75} />
          ) : (
            <>
              <button
                type="button"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => void commit()}
                aria-label={t("inlineEdit.save")}
              >
                <Check className="h-4 w-4" strokeWidth={1.75} />
              </button>
              <button
                type="button"
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                onMouseDown={(e) => e.preventDefault()}
                onClick={cancel}
                aria-label={t("inlineEdit.cancel")}
              >
                <X className="h-4 w-4" strokeWidth={1.75} />
              </button>
            </>
          )}
        </span>
      </span>
    )
  }

  const isEmpty = !value.trim()
  const displayText = isEmpty ? resolvedPlaceholder : value

  // Promote the display container to a real heading element when the caller
  // requested a heading-sized rendition. The button-as-trigger pattern stays
  // wrapped inside, so the click/keyboard/aria-label affordance is unchanged
  // — but assistive tech now sees an actual <h1>/<h2> in the page outline
  // instead of a styled <span>.
  const HeadingTag = size === "h1" ? "h1" : size === "h2" ? "h2" : "span"

  if (disabled) {
    return (
      <HeadingTag className={cn("inline-block w-full", size !== "body" && "m-0", className)}>
        <span
          className={cn(
            "text-wrap-safe",
            multiline && "whitespace-pre-line",
            sizeClasses[size],
            isEmpty && "text-muted-foreground italic",
            textClassName,
          )}
        >
          {displayText}
        </span>
      </HeadingTag>
    )
  }

  // For heading sizes we render a block-level <h1>/<h2> so the page outline
  // is correct. The original body variant kept `inline-flex` so it could sit
  // next to neighbouring text — that contract is preserved below.
  return (
    <HeadingTag
      className={cn(
        size === "body"
          ? "group/edit relative inline-flex w-full items-start gap-2"
          : "group/edit relative flex w-full items-start gap-2 m-0",
        className,
      )}
    >
      <button
        type="button"
        onClick={start}
        aria-label={ariaLabel ?? t("inlineEdit.editAria", { what: resolvedPlaceholder.toLowerCase() })}
        className={cn(
          "flex-1 min-w-0 cursor-text rounded-md px-2 py-1 text-left transition-colors text-wrap-safe hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          multiline && "whitespace-pre-line",
          sizeClasses[size],
          isEmpty && "text-muted-foreground italic",
          textClassName,
        )}
      >
        {displayText}
      </button>
      <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 opacity-0 transition-opacity group-hover/edit:opacity-100 group-focus-within/edit:opacity-100">
        <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-background/80 text-muted-foreground shadow-sm ring-1 ring-border">
          <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} />
        </span>
      </span>
    </HeadingTag>
  )
}
