import { useTranslation } from "react-i18next"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"

interface Props {
  title: string
  setTitle: (v: string) => void
  description: string
  setDescription: (v: string) => void
  passingScore: number
  setPassingScore: (v: number) => void
  maxAttempts: number
  setMaxAttempts: (v: number) => void
  chapterType: "quiz" | "exam"
}

export function QuizHeaderFields({
  title,
  setTitle,
  description,
  setDescription,
  passingScore,
  setPassingScore,
  maxAttempts,
  setMaxAttempts,
  chapterType,
}: Props) {
  const { t } = useTranslation()
  return (
    <div className="grid gap-3">
      <div className="space-y-1.5">
        <Label className="text-xs">{t("quizEditor.fields.quizTitle")}</Label>
        <Input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t("quizEditor.fields.titlePlaceholder")}
          fieldSize="sm"
          className="text-sm"
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{t("quizEditor.fields.description")}</Label>
        <Textarea
          fieldSize="sm"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t("quizEditor.fields.descriptionPlaceholder")}
          className="text-sm"
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{t("quizEditor.fields.passingScore")}</Label>
        <Input
          type="number"
          min={0}
          max={100}
          value={passingScore}
          onChange={(e) => setPassingScore(Number(e.target.value))}
          fieldSize="sm"
          className="w-28 text-sm"
        />
      </div>
      {chapterType === "exam" && (
        <div className="space-y-1.5">
          <Label className="text-xs">{t("quizEditor.fields.maxAttempts")}</Label>
          <Input
            type="number"
            min={1}
            max={10}
            value={maxAttempts}
            onChange={(e) =>
              setMaxAttempts(Math.min(10, Math.max(1, Number(e.target.value) || 1)))
            }
            fieldSize="sm"
            className="w-28 text-sm"
          />
        </div>
      )}
    </div>
  )
}
