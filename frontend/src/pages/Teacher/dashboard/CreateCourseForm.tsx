import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
        <CardTitle className="text-lg">
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
              value={form.title}
              onChange={(e) => {
                setForm((p) => ({ ...p, title: e.target.value }))
                setErrors((p) => ({ ...p, title: undefined }))
              }}
              placeholder={t("teacherDashboard.createForm.titlePlaceholder")}
            />
            {errors.title && <p className="text-sm text-destructive">{errors.title}</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="desc">
              {t("teacherDashboard.createForm.descriptionLabel")}
            </Label>
            <textarea
              id="desc"
              className="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={form.description}
              onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
              placeholder={t("teacherDashboard.createForm.descriptionPlaceholder")}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="img">
              {t("teacherDashboard.createForm.imageUrlLabel")}
            </Label>
            <Input
              id="img"
              value={form.image_url}
              onChange={(e) => setForm((p) => ({ ...p, image_url: e.target.value }))}
              placeholder={t("teacherDashboard.createForm.imageUrlPlaceholder")}
            />
            {errors.image_url && (
              <p className="text-sm text-destructive">{errors.image_url}</p>
            )}
          </div>
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
