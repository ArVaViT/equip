-- Where to watch a live session afterwards.
--
-- Half the students of a live course watch it later — in another time zone,
-- after a night shift, when the power was off. The teacher pastes the
-- recording's address on the event once it exists; the event then carries
-- it to the calendar and the course page beside the meeting link.
--
-- A plain address, like meeting_url and for the same reasons: the same
-- string in every language, kept out of the translated text, and validated
-- to http(s) by the API before it is written (app/core/meeting_url.py).

ALTER TABLE public.course_events
  ADD COLUMN IF NOT EXISTS recording_url character varying(2048);
