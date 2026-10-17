-- A weekly lesson remembers whose clock it keeps.
--
-- A series is stepped on the wall clock of the zone the teacher scheduled
-- it in, so "Saturday 19:00 in Indianapolis" stays 19:00 there after
-- November 1. Moving "this and the following" lessons later was measured
-- in the zone of whoever made the edit instead. Those agree while the
-- editor sits where the series was made; they do not when a teacher in
-- Kyiv (or one travelling, or an admin) moves an Indiana series a day: in
-- the week between Kyiv's clock change on October 25 and Indiana's on
-- November 1 the moved lesson landed an hour off on Indiana's clock.
--
-- The zone is written once, when the series is created
-- (`api/v1/calendar.create_course_event`), and read by every later move.
-- NULL for single events and for series made before this column, which
-- keep the previous rule (the editor's zone). Validated as an IANA name by
-- the API (`schemas/calendar._known_time_zone`) before it gets here.
--
-- Must be applied before the backend that writes it is deployed.

ALTER TABLE public.course_events ADD COLUMN IF NOT EXISTS time_zone character varying(64);
