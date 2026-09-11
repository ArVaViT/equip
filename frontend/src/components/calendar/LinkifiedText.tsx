import { Fragment, type ReactNode } from "react"
import { isAbsoluteHttpUrl } from "@/lib/url"

/**
 * Plain text with its web addresses made clickable.
 *
 * An event description is a free text box, and teachers put links in
 * free text boxes — the first one on this platform put his Zoom address
 * there. Rendered as bare text it is a link you cannot follow: on a
 * phone the student has to select the string by hand and paste it into
 * a browser, which is the kind of small indignity that ends with people
 * asking for the link in a chat instead.
 *
 * The text itself is never treated as markup. It is split on
 * whitespace, each token is asked whether it is a whole web address by
 * the same check the meeting-link field uses, and only those become
 * anchors. Anything else — a bare `zoom.us/j/1`, a `javascript:` value,
 * a word with a dot in it — is printed as the text it is.
 *
 * Sentence punctuation is trimmed off the end of a candidate and
 * printed after the link, so "join here: https://zoom.us/j/1." gives a
 * link that ends at the digit and a full stop that stays prose.
 */

/** Both halves of every pair, because `trim` works on each end. */
const EDGE_NOISE = ".,;:!?()[]{}<>\"'«»„“”‘’"

function trimEdges(token: string): { lead: string; core: string; tail: string } {
  let start = 0
  let end = token.length
  while (start < end && EDGE_NOISE.includes(token[start]!)) start += 1
  while (end > start && EDGE_NOISE.includes(token[end - 1]!)) end -= 1
  return {
    lead: token.slice(0, start),
    core: token.slice(start, end),
    tail: token.slice(end),
  }
}

interface Props {
  text: string
  /** Applied to every anchor; the surrounding text keeps its own style. */
  linkClassName?: string
}

export function LinkifiedText({ text, linkClassName }: Props): ReactNode {
  // Split on whitespace but keep it: the description is rendered with
  // its own line breaks, and rebuilding it with single spaces would
  // quietly reflow the teacher's text.
  const pieces = text.split(/(\s+)/)
  return (
    <>
      {pieces.map((piece, i) => {
        if (piece === "" || /^\s+$/.test(piece)) return <Fragment key={i}>{piece}</Fragment>
        const { lead, core, tail } = trimEdges(piece)
        if (!isAbsoluteHttpUrl(core)) return <Fragment key={i}>{piece}</Fragment>
        return (
          <Fragment key={i}>
            {lead}
            <a
              href={core}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className={linkClassName ?? "text-brand underline underline-offset-4"}
            >
              {core}
            </a>
            {tail}
          </Fragment>
        )
      })}
    </>
  )
}
