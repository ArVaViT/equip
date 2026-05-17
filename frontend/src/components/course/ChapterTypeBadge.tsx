import { useTranslation } from "react-i18next"
import { getChapterTypeMeta, normalizeChapterType } from "@/lib/chapterTypes"

interface Props {
  type: string
  size?: "sm" | "md"
}

export default function ChapterTypeBadge({ type, size = "md" }: Props) {
  const { t } = useTranslation()
  const normalized = normalizeChapterType(type)
  const meta = getChapterTypeMeta(type)
  const Icon = meta.icon
  const sizing =
    size === "sm"
      ? "gap-1 px-2 py-0.5 text-xs"
      : "gap-1.5 px-3 py-1 text-xs"
  const iconSize = size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${sizing} ${meta.color}`}>
      <Icon className={iconSize} strokeWidth={1.75} aria-hidden />
      {t(`chapterTypes.${normalized}.label`)}
    </span>
  )
}
