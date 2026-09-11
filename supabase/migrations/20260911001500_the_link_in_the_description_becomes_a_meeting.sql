-- The link a teacher put in the description becomes the meeting.
--
-- `course_events.meeting_url` arrived on 2026-09-07. The lesson this
-- product's first teacher scheduled was created on 2026-09-06, so he put
-- his Zoom address in the only place there was — the description — and
-- his event went out with no meeting attached: no Join button on the
-- course page, none in the calendar, nothing in the feed. From where he
-- sat, he had entered the link and the product had swallowed it.
--
-- The route now reads a link out of the description when the field is
-- blank (create, and any edit that rewrites the description). That fixes
-- what comes next; this fixes what is already there, once.
--
-- The bar matches `app/core/meeting_url.py`, which is what every other
-- path enforces:
--
--   * absolute http(s) with a host — `https?://`, and the first segment
--     is not empty;
--   * no credentials before the host — a value like
--     `https://zoom.us@evil.com/j/1` shows the half a reader trusts and
--     opens the other one, so it is refused rather than repaired;
--   * sentence punctuation trimmed off the end, because "join here:
--     https://zoom.us/j/1." ends with a full stop that is not the link.
--
-- Only rows where the column is empty are touched, and only the author's
-- own text is read (`origin = 'human'`) — never a machine translation,
-- which is a copy of the link at best and a rewrite of it at worst.
--
-- Measured on production before writing this: exactly one row qualifies,
-- the 12 September lesson of course 7924a1cf, whose description is the
-- Zoom URL and nothing else.

WITH candidate AS (
    SELECT
        e.id,
        regexp_replace(
            substring(cv.text FROM 'https?://[^[:space:]]+'),
            '[.,;:!?)\]}»"'']+$',
            ''
        ) AS url
    FROM public.course_events e
    JOIN public.content_versions cv
      ON cv.entity_type = 'course_event'
     AND cv.entity_id = e.id::text
     AND cv.field = 'description'
     AND cv.origin = 'human'
    WHERE e.meeting_url IS NULL
)
UPDATE public.course_events e
SET meeting_url = c.url
FROM candidate c
WHERE e.id = c.id
  AND c.url IS NOT NULL
  -- A host, and no userinfo in front of it.
  AND c.url ~ '^https?://[^/@]+(/|$|\?|#)';
