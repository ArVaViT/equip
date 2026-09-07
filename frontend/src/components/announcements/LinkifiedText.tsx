import { Fragment } from "react"
import { linkifySegments } from "./linkify"

interface Props {
  text: string
}

/**
 * Plain text with its links made clickable.
 *
 * An announcement body is a ``<textarea>``, and the most common thing a
 * teacher puts in one is the address of the Zoom room. Rendered as a
 * string it had to be selected and copied — on a phone, character by
 * character. Nothing else is interpreted: no markup, no markdown. Line
 * breaks are the parent's business (``whitespace-pre-line``).
 *
 * Links open in a new tab with ``rel="noopener noreferrer"`` — the page
 * a student lands on gets no handle back to Equip.
 */
export function LinkifiedText({ text }: Props) {
  const segments = linkifySegments(text)
  return (
    <>
      {segments.map((segment, i) =>
        segment.kind === "link" ? (
          <a
            key={i}
            href={segment.value}
            target="_blank"
            rel="noopener noreferrer"
            className="break-all text-brand underline underline-offset-4 hover:opacity-80"
          >
            {segment.value}
          </a>
        ) : (
          <Fragment key={i}>{segment.value}</Fragment>
        ),
      )}
    </>
  )
}
