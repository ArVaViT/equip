import {
  ClipboardList,
  FileText,
  HelpCircle,
  Paperclip,
  Type,
  type LucideIcon,
} from "lucide-react"

/**
 * The block "kinds" a teacher can add to a chapter. Video and audio
 * embeds live inside text blocks (the rich editor's toolbar has
 * dedicated buttons), so the block layer only needs the shapes that
 * aren't just HTML. Display labels live in i18n bundles at
 * `blockEditor.types.{text|quiz|assignment|file}`.
 */
export const BLOCK_TYPES = [
  { value: "text", icon: Type },
  { value: "quiz", icon: HelpCircle },
  { value: "assignment", icon: ClipboardList },
  { value: "file", icon: Paperclip },
] as const satisfies ReadonlyArray<{ value: string; icon: LucideIcon }>

export type BlockType = (typeof BLOCK_TYPES)[number]["value"]

export function blockIcon(type: string): LucideIcon {
  return BLOCK_TYPES.find((bt) => bt.value === type)?.icon ?? FileText
}

// Static i18n key lookup so callers ``t(BLOCK_TYPE_LABEL_KEYS[type])``
// instead of ``t(`blockEditor.types.${type}`)`` — keeps the keys
// visible to the i18n keyCoverage static check.
export const BLOCK_TYPE_LABEL_KEYS: Record<BlockType, string> = {
  text: "blockEditor.types.text",
  quiz: "blockEditor.types.quiz",
  assignment: "blockEditor.types.assignment",
  file: "blockEditor.types.file",
}
