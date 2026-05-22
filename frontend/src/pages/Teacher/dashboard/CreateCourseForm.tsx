import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import type { CourseFormData } from "@/lib/validations/course"

interface Props {
  form: CourseFormData
  setForm: React.Dispatch<React.SetStateAction<CourseFormData>>
  errors: Partial<Record<string, string>>
  setErrors: React.Dispatch<React.SetStateAction<Partial<Record<string, string>>>>
  saving: boolean
  onSubmit: (e: React.FormEvent) => void
  onCancel: () => void
}

// Intentionally minimal: only ``title`` is required to land in the
// editor. ``description`` is optional. Cover image, modules, calendar,
// access mode, etc. all live in the editor — pushing every setting
// into this gate scared first-time teachers off before they ever saw
// the editor at all.
export function CreateCourseForm({
  form,
  setForm,
  errors,
  setErrors,
  saving,
  onSubmit,
  onCancel,
}: Props) {
  const { t } = useTranslation()
  return (
    <Card className="mb-8 border-dashed">
      <CardHeader>
        <CardTitle className="font-serif text-lg font-semibold tracking-tight">
          {t("teacherDashboard.createForm.title")}
        </CardTitle>
      </CardHeader>
      <form onSubmit={onSubmit}>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="title">
              {t("teacherDashboard.createForm.titleLabel")}
            </Label>
            <Input
              id="title"
              autoFocus
              maxLength={200}
              value={form.title}
              onChange={(e) => {
                // Cap at 200 chars to match the server-side schema
                // (``makeCourseSchema`` already enforces this, and so
                // does CourseEditor's title field). Without ``maxLength``
                // a paste of a 5000-char string was POSTed and rejected
                // with a generic 400, costing one network round-trip
                // and an opaque error.
                setForm((p) => ({ ...p, title: e.target.value.slice(0, 200) }))
                setErrors((p) => ({ ...p, title: undefined }))
              }}
              placeholder={t("teacherDashboard.createForm.titlePlaceholder")}
            />
            {errors.title && <p className="text-sm text-destructive">{errors.title}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="desc">
              {t("teacherDashboard.createForm.descriptionLabel")}
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {t("teacherDashboard.createForm.optional")}
              </span>
            </Label>
            <Textarea
              id="desc"
              fieldSize="default"
              maxLength={2000}
              className="min-h-[80px]"
              value={form.description}
              onChange={(e) =>
                setForm((p) => ({ ...p, description: e.target.value.slice(0, 2000) }))
              }
              placeholder={t("teacherDashboard.createForm.descriptionPlaceholder")}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {t("teacherDashboard.createForm.editorHint")}
          </p>
          <div className="flex gap-2 pt-2">
            <Button type="submit" disabled={saving}>
              {saving
                ? t("teacherDashboard.createForm.creating")
                : t("teacherDashboard.createForm.submit")}
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel}>
              {t("teacherDashboard.createForm.cancel")}
            </Button>
          </div>
        </CardContent>
      </form>
    </Card>
  )
}
