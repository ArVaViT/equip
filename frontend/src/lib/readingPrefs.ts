import { useCallback, useState } from "react"

/**
 * How a reader likes a lesson set: text size and "easy reading" (looser
 * lines and spacing). Kept on the device — a phone read in bed and a desktop
 * at work rarely want the same — and never required: storage that throws
 * (private mode, blocked site data) just means the defaults.
 */
export type ReadingSize = "s" | "m" | "l" | "xl"
export interface ReadingPrefs {
  size: ReadingSize
  easy: boolean
}

export const READING_SIZES: ReadingSize[] = ["s", "m", "l", "xl"]
const KEY = "equip:reading"
const DEFAULTS: ReadingPrefs = { size: "m", easy: false }

export function loadReadingPrefs(): ReadingPrefs {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "null") as Partial<ReadingPrefs> | null
    return {
      size: raw && READING_SIZES.includes(raw.size as ReadingSize) ? (raw.size as ReadingSize) : DEFAULTS.size,
      easy: raw?.easy === true,
    }
  } catch {
    return DEFAULTS
  }
}

export function useReadingPrefs(): [ReadingPrefs, (next: Partial<ReadingPrefs>) => void] {
  const [prefs, setPrefs] = useState<ReadingPrefs>(loadReadingPrefs)
  const update = useCallback((next: Partial<ReadingPrefs>) => {
    setPrefs((current) => {
      const merged = { ...current, ...next }
      try {
        localStorage.setItem(KEY, JSON.stringify(merged))
      } catch {
        /* the choice lasts this page, not the visit */
      }
      return merged
    })
  }, [])
  return [prefs, update]
}
