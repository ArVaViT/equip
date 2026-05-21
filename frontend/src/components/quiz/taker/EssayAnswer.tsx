import { useTranslation } from "react-i18next"
import { Textarea } from "@/components/ui/textarea"
import { countWords } from "@/lib/text"

interface Props {
  value: string
  minWords: number | null
  onChange: (text: string) => void
}

export function EssayAnswer({ value, minWords, onChange }: Props) {
  const { t } = useTranslation()
  const words = countWords(value)
  const minReached = !minWords || words >= minWords
  return (
    <div className="ml-9 space-y-1.5">
      <Textarea
        fieldSize="default"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={
          minWords
            ? t("quiz.essayPlaceholderMin", { count: minWords })
            : t("quiz.essayPlaceholder")
        }
        className="min-h-[220px]"
      />
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{t("quiz.essayHelper")}</span>
        <span className={minReached ? "text-muted-foreground" : "text-warning font-medium"}>
          {minWords
            ? t("quiz.wordsWithMin", { count: words, min: minWords })
            : t("quiz.wordsCount", { count: words })}
        </span>
      </div>
    </div>
  )
}
