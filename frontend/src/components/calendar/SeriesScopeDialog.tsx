import { useState } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Modal } from "@/components/patterns"
import type { SeriesScope } from "@/services/calendar"

const SCOPES: readonly SeriesScope[] = ["this", "following", "all"]

/**
 * "This lesson, this and the following, or the whole series?" — asked when
 * a teacher saves or deletes one occurrence of a weekly series. The answer
 * defaults to "this": the narrowest change is the one that cannot surprise.
 */
export function SeriesScopeDialog({
  open,
  action,
  onChoose,
  onCancel,
}: {
  open: boolean
  action: "save" | "delete"
  onChoose: (scope: SeriesScope) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const [scope, setScope] = useState<SeriesScope>("this")
  const title = action === "save" ? t("eventSeries.scope.saveTitle") : t("eventSeries.scope.deleteTitle")
  return (
    <Modal open={open} onClose={onCancel} title={title}>
      <RadioGroup value={scope} onValueChange={(v) => setScope(v as SeriesScope)} className="space-y-2">
        {SCOPES.map((value) => (
          <div key={value} className="flex items-center gap-2">
            <RadioGroupItem id={`series-scope-${value}`} value={value} />
            <Label htmlFor={`series-scope-${value}`} className="text-sm font-normal">
              {t(`eventSeries.scope.${value}`)}
            </Label>
          </div>
        ))}
      </RadioGroup>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button
          size="sm"
          variant={action === "delete" ? "destructive" : "default"}
          onClick={() => {
            onChoose(scope)
            setScope("this")
          }}
        >
          {action === "save" ? t("eventSeries.scope.saveAction") : t("eventSeries.scope.deleteAction")}
        </Button>
      </div>
    </Modal>
  )
}
