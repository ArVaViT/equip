import type { TFunction } from "i18next"
import { formatNumber } from "@/i18n/number"

const KB = 1024
const MB = KB * 1024

/**
 * File size for a person to read: B, KB or MB, whichever keeps the
 * number sensible. A 16 KB outline printed in MB reads «0,0 МБ», which
 * looks like an empty upload — a student saw exactly that on a real
 * submission (2026-11-08). ``prefix`` is the i18n block that holds
 * ``sizeBytes`` / ``sizeKb`` / ``sizeMb``.
 *
 * The number goes through ``formatNumber`` because ``toFixed`` writes a
 * period and ru / de / uk all write a comma.
 */
export function formatFileSize(bytes: number, t: TFunction, prefix: string): string {
  if (bytes < KB) return t(`${prefix}.sizeBytes`, { b: bytes })
  if (bytes < MB) return t(`${prefix}.sizeKb`, { kb: formatNumber(bytes / KB, 0) })
  return t(`${prefix}.sizeMb`, { mb: formatNumber(bytes / MB, 1) })
}
