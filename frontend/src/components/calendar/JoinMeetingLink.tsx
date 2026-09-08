import { Video } from "lucide-react"
import { useTranslation } from "react-i18next"

import { isAbsoluteHttpUrl } from "@/lib/url"
import { cn } from "@/lib/utils"

interface Props {
  /** The event's meeting link. Absent, blank or unsafe renders nothing. */
  url: string | null | undefined
  /** The event's title, for the screen-reader label. A row can hold
   *  several of these and "Join" alone does not say which class. */
  title: string
  className?: string
}

/**
 * The way into a live session, as a thing you press.
 *
 * A bare address is not an invitation. Before this, a teacher's Zoom
 * link sat in the event description as text: on a phone it had to be
 * selected character by character to be copied, and on every surface it
 * competed with the title for the row's width. So the address is not
 * shown at all — the action is.
 *
 * Renders nothing at all when there is no link, which is most events.
 * A deadline has nowhere to be, and an empty button that goes nowhere
 * is worse than no button: it is a promise the row cannot keep.
 *
 * `isAbsoluteHttpUrl` is the second lock on the same door. The server
 * refuses anything but `http(s)` on the way in, so a `javascript:` here
 * would mean that check had already failed — but React puts whatever it
 * is given into `href`, and a scheme it does not like is not one of the
 * things it escapes. A stored `javascript:` in an `href` runs in the
 * reader's session, with the reader's cookies, the moment they click
 * something that says "Join". The cost of checking again is one
 * `new URL()`; the cost of not checking is every student who clicks.
 *
 * `rel="noopener noreferrer"` with `target="_blank"`: the meeting opens
 * beside the lesson rather than on top of it, and the page that opens
 * gets no `window.opener` handle back to Equip.
 */
export function JoinMeetingLink({ url, title, className }: Props) {
  const { t } = useTranslation()
  if (!isAbsoluteHttpUrl(url)) return null
  return (
    <a
      href={url as string}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={t("meeting.joinAria", { title })}
      // Stops the row's own click handler where there is one — the
      // notification row and the calendar cell are both buttons, and
      // joining is not the same as opening.
      onClick={(e) => e.stopPropagation()}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-md border border-brand/30 bg-brand/5 px-2 py-1",
        "text-xs font-medium text-brand transition-colors hover:bg-brand/10",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2",
        className,
      )}
    >
      <Video className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden />
      {t("meeting.join")}
    </a>
  )
}
