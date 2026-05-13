import { useTranslation } from "react-i18next"
import { GraduationCap } from "lucide-react"

export type QuizEditorMode = "edit" | "review"

interface Props {
  mode: QuizEditorMode
  setMode: (mode: QuizEditorMode) => void
}

export function ModeToggle({ mode, setMode }: Props) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center rounded-md border bg-background p-0.5 text-xs">
      <button
        type="button"
        onClick={() => setMode("edit")}
        className={`px-2.5 py-1 rounded-sm transition-colors ${
          mode === "edit"
            ? "bg-muted font-medium"
            : "text-muted-foreground hover:text-foreground"
        }`}
      >
        {t("quizEditor.modeToggle.edit")}
      </button>
      <button
        type="button"
        onClick={() => setMode("review")}
        className={`flex items-center gap-1 px-2.5 py-1 rounded-sm transition-colors ${
          mode === "review"
            ? "bg-muted font-medium"
            : "text-muted-foreground hover:text-foreground"
        }`}
      >
        <GraduationCap className="h-3.5 w-3.5" />
        {t("quizEditor.modeToggle.submissions")}
      </button>
    </div>
  )
}
