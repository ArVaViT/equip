import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate, useParams } from "react-router-dom"
import { Check, Languages, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState, PageHeader } from "@/components/patterns"
import { Badge } from "@/components/ui/badge"
import { usePrompt } from "@/components/ui/alert-dialog"
import {
  adminDailyChallengeService,
  type AdminDailyChallengeBilingualView,
  type AdminDailyChallengeCvCell,
} from "@/services/adminDailyChallenge"
import { getErrorDetail } from "@/lib/errorDetail"

type Field = "question_text" | "explanation"

/**
 * Side-by-side editor for a single Daily Challenge question's
 * bilingual cv rows. Two columns (EN / RU); inline-editable per
 * field/option. Saves go through ``POST .../cv``. Approve flow
 * promotes the question one stage forward; reject opens a confirm
 * + writes the reason via the existing reject endpoint.
 */
export default function DailyChallengeReviewDetailPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const prompt = usePrompt()
  const { questionId } = useParams<{ questionId: string }>()

  const [view, setView] = useState<AdminDailyChallengeBilingualView | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [saving, setSaving] = useState(false)
  const [promoting, setPromoting] = useState(false)

  const load = useCallback(async () => {
    if (!questionId) return
    setLoading(true)
    setLoadError(false)
    try {
      const v = await adminDailyChallengeService.getBilingualView(questionId)
      setView(v)
    } catch {
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }, [questionId])

  useEffect(() => {
    void load()
  }, [load])

  const saveCv = useCallback(
    async (params: { field: "question_text" | "explanation" | "option_text"; locale: "en" | "ru"; text: string; option_id?: string }) => {
      if (!questionId) return
      setSaving(true)
      try {
        await adminDailyChallengeService.upsertCv(questionId, params)
        toast.success(t("admin.dailyChallenge.review.toast.saved"))
        await load()
      } catch (err) {
        toast.error(getErrorDetail(err) || t("admin.dailyChallenge.review.toast.saveError"))
      } finally {
        setSaving(false)
      }
    },
    [questionId, t, load],
  )

  const promote = useCallback(async () => {
    if (!questionId) return
    setPromoting(true)
    try {
      await adminDailyChallengeService.promote(questionId)
      toast.success(t("admin.dailyChallenge.review.toast.promoted"))
      navigate("/admin/daily-challenge/review")
    } catch (err) {
      toast.error(getErrorDetail(err) || t("admin.dailyChallenge.review.toast.promoteError"))
    } finally {
      setPromoting(false)
    }
  }, [questionId, t, navigate])

  const reject = useCallback(async () => {
    if (!questionId) return
    const reason = await prompt({
      title: t("admin.dailyChallenge.review.rejectPrompt"),
      confirmLabel: t("admin.dailyChallenge.review.reject"),
      cancelLabel: t("common.cancel"),
    })
    if (!reason || !reason.trim()) return
    try {
      await adminDailyChallengeService.reject(questionId, reason.trim())
      toast.success(t("admin.dailyChallenge.review.toast.rejected"))
      navigate("/admin/daily-challenge/review")
    } catch (err) {
      toast.error(getErrorDetail(err) || t("admin.dailyChallenge.review.toast.rejectError"))
    }
  }, [questionId, prompt, t, navigate])

  return (
    <div className="container mx-auto max-w-5xl px-4 py-6 sm:py-8">
      <PageHeader
        backTo="/admin/daily-challenge/review"
        backLabel={t("admin.dailyChallenge.review.backToQueue")}
        title={
          <h1 className="flex items-center gap-2 font-serif text-xl font-bold tracking-tight sm:text-2xl">
            <Languages className="h-5 w-5 text-brand" strokeWidth={1.75} aria-hidden />
            {view
              ? `${view.bible_book} ${view.bible_chapter}${
                  view.bible_verse_from != null ? `:${view.bible_verse_from}` : ""
                }`
              : t("admin.dailyChallenge.review.detailTitle")}
          </h1>
        }
        actions={
          view && (
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" onClick={() => void reject()}>
                {t("admin.dailyChallenge.review.reject")}
              </Button>
              <Button
                size="sm"
                onClick={() => void promote()}
                disabled={promoting || saving || view.rejected}
              >
                <Check className="mr-1.5 h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
                {t("admin.dailyChallenge.review.approve")}
              </Button>
            </div>
          )
        }
      />

      {loading ? (
        <div className="mt-6 space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : loadError ? (
        <ErrorState
          className="mt-6"
          title={t("admin.dailyChallenge.review.loadError")}
          action={
            <Button size="sm" variant="outline" onClick={load}>
              {t("common.tryAgain")}
            </Button>
          }
        />
      ) : view ? (
        <div className="mt-6 space-y-6">
          {view.rejected && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {t("admin.dailyChallenge.review.rejectedBanner", { reason: view.rejection_reason ?? "" })}
            </div>
          )}
          <FieldEditor
            label={t("admin.dailyChallenge.review.field.questionText")}
            field="question_text"
            cells={view.question_text}
            saving={saving}
            onSave={saveCv}
          />
          <FieldEditor
            label={t("admin.dailyChallenge.review.field.explanation")}
            field="explanation"
            cells={view.explanation}
            saving={saving}
            onSave={saveCv}
          />
          <section className="space-y-3">
            <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-ink-muted">
              {t("admin.dailyChallenge.review.options")}
            </h3>
            {view.options.map((opt) => (
              <FieldEditor
                key={opt.id}
                label={
                  <span className="flex items-center gap-2">
                    {String.fromCharCode(65 + opt.order_index)}.
                    {opt.is_correct && (
                      <Badge variant="primarySubtle">
                        <Check className="mr-1 h-3 w-3" strokeWidth={1.75} aria-hidden />
                        {t("admin.dailyChallenge.review.correct")}
                      </Badge>
                    )}
                  </span>
                }
                field="option_text"
                cells={{ en: opt.en, ru: opt.ru }}
                optionId={opt.id}
                saving={saving}
                onSave={saveCv}
              />
            ))}
          </section>
        </div>
      ) : null}
    </div>
  )
}

interface FieldEditorProps {
  label: React.ReactNode
  field: Field | "option_text"
  cells: Record<"en" | "ru", AdminDailyChallengeCvCell>
  optionId?: string
  saving: boolean
  onSave: (params: {
    field: "question_text" | "explanation" | "option_text"
    locale: "en" | "ru"
    text: string
    option_id?: string
  }) => Promise<void>
}

function FieldEditor({ label, field, cells, optionId, saving, onSave }: FieldEditorProps) {
  return (
    <div className="rounded-md border border-edge dark:border-transparent bg-card p-4">
      <div className="mb-3 text-xs font-medium uppercase tracking-[0.14em] text-ink-muted">{label}</div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <LocaleCellEditor
          locale="en"
          cell={cells.en}
          saving={saving}
          onSave={(text) => onSave({ field, locale: "en", text, option_id: optionId })}
        />
        <LocaleCellEditor
          locale="ru"
          cell={cells.ru}
          saving={saving}
          onSave={(text) => onSave({ field, locale: "ru", text, option_id: optionId })}
        />
      </div>
    </div>
  )
}

interface LocaleCellEditorProps {
  locale: "en" | "ru"
  cell: AdminDailyChallengeCvCell
  saving: boolean
  onSave: (text: string) => Promise<void>
}

function LocaleCellEditor({ locale, cell, saving, onSave }: LocaleCellEditorProps) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState(cell.text)
  const [editing, setEditing] = useState(false)

  useEffect(() => {
    setDraft(cell.text)
    setEditing(false)
  }, [cell.text, cell.cv_id])

  const dirty = draft !== cell.text
  const missing = cell.cv_id === null

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-muted">
          {locale.toUpperCase()}
        </span>
        {missing ? (
          <Badge variant="destructiveSubtle">
            <X className="mr-1 h-3 w-3" strokeWidth={1.75} aria-hidden />
            {t("admin.dailyChallenge.review.missing")}
          </Badge>
        ) : cell.origin === "human" ? (
          <Badge variant="primarySubtle">{t("admin.dailyChallenge.review.originHuman")}</Badge>
        ) : (
          <Badge variant="infoSubtle">{t("admin.dailyChallenge.review.originMt")}</Badge>
        )}
      </div>
      <textarea
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value)
          setEditing(true)
        }}
        rows={3}
        placeholder={missing ? t("admin.dailyChallenge.review.fillPlaceholder") : undefined}
        className="w-full rounded-md bg-surface px-2 py-1.5 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      />
      {(editing || dirty) && (
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setDraft(cell.text)
              setEditing(false)
            }}
            disabled={saving}
          >
            {t("common.cancel")}
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={saving || !dirty || !draft.trim()}
            onClick={() => void onSave(draft.trim())}
          >
            {t("admin.dailyChallenge.review.save")}
          </Button>
        </div>
      )}
    </div>
  )
}
