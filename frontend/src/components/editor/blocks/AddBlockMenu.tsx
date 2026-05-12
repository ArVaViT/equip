import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Loader2, Plus } from "lucide-react"
import { BLOCK_TYPES, type BlockType } from "./types"

interface Props {
  onAdd: (type: BlockType) => void
  adding: boolean
}

/**
 * "Add Block" button with a dropdown of block types. Self-contained —
 * the parent just exposes an `onAdd(type)` callback.
 */
export function AddBlockMenu({ onAdd, adding }: Props) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  const pick = (type: BlockType) => {
    setOpen(false)
    onAdd(type)
  }

  return (
    <div className="relative">
      <Button
        variant="outline"
        size="sm"
        className="w-full border-dashed"
        onClick={() => setOpen((v) => !v)}
        disabled={adding}
      >
        {adding ? (
          <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
        ) : (
          <Plus className="h-3.5 w-3.5 mr-1.5" />
        )}
        {t("blockEditor.addBlock")}
      </Button>
      {open && (
        <div className="absolute z-10 mt-1 w-full bg-background border rounded-md shadow-lg py-1">
          {BLOCK_TYPES.map((bt) => {
            const Icon = bt.icon
            return (
              <button
                key={bt.value}
                onClick={() => pick(bt.value)}
                className="flex items-center gap-2 w-full px-3 py-2 text-sm hover:bg-muted transition-colors text-left"
              >
                <Icon className="h-4 w-4 text-muted-foreground" />
                {t(`blockEditor.types.${bt.value}`)}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
