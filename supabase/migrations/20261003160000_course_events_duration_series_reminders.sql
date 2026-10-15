-- Course events get a length, a series and a reminder stamp (2026-10-03).
--
-- duration_minutes — an event carried a start and nothing else, so every
--   calendar guessed: the iCal feed wrote one hour, the app called a
--   class over three hours after it began. NULL stays legal: a deadline
--   is a moment, not a span.
-- series_id — "every Saturday at 20:00" was twelve events typed by hand.
--   A weekly series is stored as its occurrences, each a real row, so a
--   single lesson can still be moved, cancelled or given its own
--   recording; the shared id is what "this and following" edits act on.
-- reminded_at — the hour-before reminder is sent once; this is the once.

alter table public.course_events
  add column if not exists duration_minutes integer,
  add column if not exists series_id uuid,
  add column if not exists reminded_at timestamp with time zone;

alter table public.course_events
  drop constraint if exists course_events_duration_minutes_check;
alter table public.course_events
  add constraint course_events_duration_minutes_check
  check (duration_minutes is null or (duration_minutes >= 1 and duration_minutes <= 1440));

create index if not exists ix_course_events_series_id
  on public.course_events using btree (series_id) where (series_id is not null);

-- The reminder sweep asks "what starts in the next hour and has not been
-- announced"; without this it reads the whole table every five minutes.
create index if not exists ix_course_events_unreminded
  on public.course_events using btree (event_date) where (reminded_at is null);
