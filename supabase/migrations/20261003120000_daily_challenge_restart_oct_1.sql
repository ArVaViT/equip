-- Daily Challenge starts over on 2026-10-01 (2026-10-03).
--
-- The calendar ran from 2026-05-31, and almost nobody played it: 7 attempts
-- and 6 streak rows in four months. Rather than leave 123 questions in the
-- past where no one saw them, the whole list is replayed from October 1 in
-- its original order — question #1 lands on 10-01, #277 on 2027-07-04 — and
-- the old answers and streaks go, since they belong to dates that now carry
-- other questions.
--
-- challenge_date is the primary key, so an in-place UPDATE would collide
-- with the next row mid-statement; the mapping is taken first, then the
-- rows are rewritten. Replenishment keeps appending after the last date.

begin;

create temporary table dc_restart_map on commit drop as
select question_id,
       scheduled_by,
       scheduled_at,
       date '2026-10-01' + (row_number() over (order by challenge_date) - 1)::int as challenge_date
from public.daily_challenge_schedule;

delete from public.daily_challenge_attempts;
delete from public.daily_challenge_streaks;
delete from public.daily_challenge_schedule;

insert into public.daily_challenge_schedule (challenge_date, question_id, scheduled_by, scheduled_at)
select challenge_date, question_id, scheduled_by, scheduled_at
from dc_restart_map;

commit;
