import type { ReactNode } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  /** ``wide`` for lists of files and other rows that read badly at 512px:
      names get truncated and four rows already need scrolling. */
  size?: "default" | "wide"
}

export function Modal({ open, onClose, title, children, size = "default" }: ModalProps) {
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      {/* Mobile uses the primitive's bottom-sheet defaults (full-width, slides
          up, safe-area aware). sm+ keeps the centered card with a max-h cap. */}
      <DialogContent
        className={`sm:max-h-[85vh] sm:overflow-y-auto${size === "wide" ? " sm:max-w-2xl" : ""}`}
      >
        <DialogHeader>
          <DialogTitle className="font-serif">{title}</DialogTitle>
        </DialogHeader>
        <div className="pt-2">{children}</div>
      </DialogContent>
    </Dialog>
  )
}
