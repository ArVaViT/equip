import { toast as sonnerToast } from "sonner"

type Variant = "default" | "destructive" | "success" | "warning" | "info"

interface ToastOptions {
  title?: string
  description?: string
  variant?: Variant
  /** One button on the toast — "Undo" after a delete. */
  action?: { label: string; onClick: () => void }
  /** Milliseconds; longer when there is something to act on. */
  duration?: number
}

type SonnerOpts = { description?: string; action?: { label: string; onClick: () => void }; duration?: number }

const SONNER_BY_VARIANT: Record<Variant, (message: string, opts?: SonnerOpts) => string | number> = {
  default: sonnerToast,
  destructive: sonnerToast.error,
  success: sonnerToast.success,
  warning: sonnerToast.warning,
  info: sonnerToast.info,
}

export function toast({ title, description, variant = "default", action, duration }: ToastOptions) {
  const body = title ?? description ?? ""
  const opts: SonnerOpts = {}
  if (title && description) opts.description = description
  if (action) opts.action = action
  if (duration) opts.duration = duration
  SONNER_BY_VARIANT[variant](body, Object.keys(opts).length ? opts : undefined)
}
