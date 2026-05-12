import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { DraftOption, DraftQuestion } from "./types"

interface Props {
  question: DraftQuestion
  index: number
  total: number
  onRemove: () => void
  onMove: (direction: "up" | "down") => void
  onUpdate: (patch: Partial<DraftQuestion>) => void
  onAddOption: () => void
  onRemoveOption: (oIdx: number) => void
  onUpdateOption: (oIdx: number, patch: Partial<DraftOption>) => void
}

export function QuestionCard({
  question: q,
  index: qIdx,
  total,
  onRemove,
  onMove,
  onUpdate,
  onAddOption,
  onRemoveOption,
  onUpdateOption,
}: Props) {
  const { t } = useTranslation()
  return (
    <Card className="bg-muted/30">
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start gap-2">
          <div className="flex flex-col gap-0.5 shrink-0 mt-1">
            <button
              type="button"
              onClick={() => onMove("up")}
              disabled={qIdx === 0}
              className="p-0.5 rounded hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed text-muted-foreground"
            >
              <ArrowUp className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => onMove("down")}
              disabled={qIdx === total - 1}
              className="p-0.5 rounded hover:bg-muted disabled:opacity-30 disabled:cursor-not-allowed text-muted-foreground"
            >
              <ArrowDown className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex-1 space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-muted-foreground">
                {t("quizEditor.questions.questionPrefix", { n: qIdx + 1 })}
              </span>
              <Input
                value={q.question_text}
                onChange={(e) => onUpdate({ question_text: e.target.value })}
                placeholder={t("quizEditor.questions.questionPlaceholder")}
                className="h-8 text-sm flex-1"
              />
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive h-7 w-7 p-0 shrink-0"
                onClick={onRemove}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>

            <div className="flex items-center gap-3">
              <select
                value={q.question_type}
                onChange={(e) =>
                  onUpdate({
                    question_type: e.target.value as DraftQuestion["question_type"],
                  })
                }
                className="h-7 rounded-md border border-input bg-background px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="multiple_choice">{t("quizEditor.questions.types.multiple_choice")}</option>
                <option value="true_false">{t("quizEditor.questions.types.true_false")}</option>
                <option value="short_answer">{t("quizEditor.questions.types.short_answer")}</option>
                <option value="essay">{t("quizEditor.questions.types.essay")}</option>
              </select>
              {q.question_type === "essay" && (
                <div className="flex items-center gap-1">
                  <Label className="text-xs text-muted-foreground">
                    {t("quizEditor.questions.minWords")}
                  </Label>
                  <Input
                    type="number"
                    min={1}
                    placeholder="—"
                    value={q.min_words ?? ""}
                    onChange={(e) =>
                      onUpdate({
                        min_words:
                          e.target.value === ""
                            ? null
                            : Math.max(1, Number(e.target.value) || 1),
                      })
                    }
                    className="h-7 text-xs w-20"
                  />
                </div>
              )}
              <div className="flex items-center gap-1">
                <Label className="text-xs text-muted-foreground">
                  {t("quizEditor.questions.points")}
                </Label>
                <Input
                  type="number"
                  min={1}
                  value={q.points}
                  onChange={(e) => onUpdate({ points: Number(e.target.value) || 1 })}
                  className="h-7 text-xs w-16"
                />
              </div>
            </div>

            {q.question_type === "multiple_choice" && (
              <div className="space-y-2">
                {q.options.map((opt, oIdx) => (
                  <div key={opt.id} className="flex items-center gap-2">
                    <input
                      type="radio"
                      name={`correct-${q.id}`}
                      checked={opt.is_correct}
                      onChange={() => onUpdateOption(oIdx, { is_correct: true })}
                      className="accent-primary shrink-0"
                      title={t("quizEditor.questions.markCorrect")}
                    />
                    <Input
                      value={opt.option_text}
                      onChange={(e) =>
                        onUpdateOption(oIdx, { option_text: e.target.value })
                      }
                      placeholder={t("quizEditor.questions.optionPlaceholder", { n: oIdx + 1 })}
                      className="h-7 text-xs flex-1"
                    />
                    {q.options.length > 2 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive shrink-0"
                        onClick={() => onRemoveOption(oIdx)}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                ))}
                <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={onAddOption}>
                  <Plus className="h-3 w-3 mr-1" />
                  {t("quizEditor.questions.addOption")}
                </Button>
              </div>
            )}

            {q.question_type === "true_false" && (
              <div className="flex gap-3">
                {q.options.map((opt, oIdx) => (
                  <label
                    key={opt.id}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-md border text-xs cursor-pointer ${
                      opt.is_correct
                        ? "border-success/50 bg-success/10"
                        : "border-border"
                    }`}
                  >
                    <input
                      type="radio"
                      name={`correct-${q.id}`}
                      checked={opt.is_correct}
                      onChange={() => onUpdateOption(oIdx, { is_correct: true })}
                      className="accent-primary"
                    />
                    {opt.option_text}
                  </label>
                ))}
              </div>
            )}

            {q.question_type === "short_answer" && (
              <p className="text-xs text-muted-foreground italic">
                {t("quizEditor.questions.shortAnswerHint")}
              </p>
            )}

            {q.question_type === "essay" && (
              <p className="text-xs text-muted-foreground italic">
                {t("quizEditor.questions.essayHint")}
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
