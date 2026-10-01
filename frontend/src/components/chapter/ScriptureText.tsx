import { Fragment, useState } from "react"
import { useTranslation } from "react-i18next"

import { useAsyncData } from "@/hooks/useAsyncData"
import { scriptureService, type Passage } from "@/services/scripture"
import { VerseCard } from "./VerseCard"

function escape(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/**
 * Plain text in which a cited verse opens over the page — the same card as
 * in a lesson, for text that is not lesson HTML (an assignment's brief).
 * The server decides what is a reference; until it answers, and when it
 * finds none or fails, this is the text exactly as written.
 */
export function ScriptureText({ text }: { text: string }) {
  const { t, i18n } = useTranslation()
  const { data } = useAsyncData(() => scriptureService.passagesIn(text), [text, i18n.language])
  const [open, setOpen] = useState<{ anchor: HTMLElement; passage: Passage } | null>(null)
  const passages = data ?? []
  if (passages.length === 0) return <>{text}</>

  const byWritten = new Map(passages.map((p) => [p.written, p]))
  const pattern = new RegExp(
    `(?<![\\p{L}\\d])(${[...byWritten.keys()]
      .sort((a, b) => b.length - a.length)
      .map((w) => escape(w).replace(/\s+/g, "[\\s\\u00a0]+"))
      .join("|")})(?!\\d)`,
    "gu",
  )
  const parts: (string | Passage)[] = []
  let at = 0
  for (const m of text.matchAll(pattern)) {
    if (m.index === undefined) continue
    const passage = byWritten.get(m[0]) ?? [...byWritten.values()].find((p) => p.written.replace(/\s+/g, " ") === m[0].replace(/\s+/g, " "))
    if (!passage) continue
    parts.push(text.slice(at, m.index), passage)
    at = m.index + m[0].length
  }
  parts.push(text.slice(at))

  return (
    <>
      {parts.map((part, i) =>
        typeof part === "string" ? (
          <Fragment key={i}>{part}</Fragment>
        ) : (
          <button
            key={i}
            type="button"
            className="verse-ref"
            aria-haspopup="dialog"
            aria-label={t("scripture.open", { ref: part.written })}
            onClick={(e) => {
              const anchor = e.currentTarget
              setOpen((current) => (current?.anchor === anchor ? null : { anchor, passage: part }))
            }}
          >
            {part.written}
          </button>
        ),
      )}
      {open && <VerseCard anchor={open.anchor} passage={open.passage} onClose={() => setOpen(null)} />}
    </>
  )
}
