--
-- PostgreSQL database dump
--

\restrict 2XKTDS5XRmU2AGeGBdr3ouCL2xQnTL8Lw6qQrf0bhJatveYzrTmxtUS4acfUht6

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: content_versions_set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.content_versions_set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;


--
-- Name: custom_access_token_hook(jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.custom_access_token_hook(event jsonb) RETURNS jsonb
    LANGUAGE plpgsql STABLE
    SET search_path TO 'pg_catalog', 'public'
    AS $$ DECLARE claims jsonb; user_role text; BEGIN SELECT role INTO user_role FROM public.profiles WHERE id = (event->>'user_id')::uuid; claims := event->'claims'; claims := jsonb_set(claims, '{user_role}', to_jsonb(COALESCE(user_role, 'student'))); event := jsonb_set(event, '{claims}', claims); RETURN event; END; $$;


--
-- Name: dc_schedule_assert_publishable(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.dc_schedule_assert_publishable() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'public'
    AS $$
DECLARE q_status TEXT; q_rejected BOOLEAN; q_pub TIMESTAMPTZ;
BEGIN
    SELECT status, rejected, published_at INTO q_status, q_rejected, q_pub
      FROM daily_challenge_questions WHERE id = NEW.question_id;
    IF q_status IS DISTINCT FROM 'published' THEN
        RAISE EXCEPTION 'daily_challenge_schedule.question_id % is not at status=published (current: %)', NEW.question_id, q_status USING ERRCODE = 'check_violation';
    END IF;
    IF q_rejected THEN
        RAISE EXCEPTION 'daily_challenge_schedule.question_id % is rejected; cannot schedule', NEW.question_id USING ERRCODE = 'check_violation';
    END IF;
    IF q_pub IS NULL THEN
        RAISE EXCEPTION 'daily_challenge_schedule.question_id % has NULL published_at', NEW.question_id USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;


--
-- Name: handle_new_user(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.handle_new_user() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO ''
    AS $$
DECLARE
  claimed_role text := NEW.raw_user_meta_data->>'role';
  safe_role text;
BEGIN
  safe_role := CASE
    WHEN claimed_role = 'student' THEN 'student'
    ELSE 'student'
  END;

  INSERT INTO public.profiles (id, email, full_name, role, preferred_locale)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
    safe_role,
    CASE
      WHEN NEW.raw_user_meta_data->>'preferred_locale' IN ('ru', 'en')
        THEN NEW.raw_user_meta_data->>'preferred_locale'
      ELSE 'ru'
    END
  )
  ON CONFLICT (id) DO UPDATE
  SET
    email = EXCLUDED.email,
    full_name = CASE
      WHEN EXCLUDED.full_name <> ''
        THEN EXCLUDED.full_name
      ELSE public.profiles.full_name
    END;
  RETURN NEW;
END;
$$;


--
-- Name: profiles_protect_immutable_fields(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.profiles_protect_immutable_fields() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
  IF current_user <> 'authenticated' THEN
    RETURN NEW;
  END IF;
  IF NEW.id IS DISTINCT FROM OLD.id THEN
    RAISE EXCEPTION 'profiles.id is immutable from client writes'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.role IS DISTINCT FROM OLD.role THEN
    RAISE EXCEPTION 'profiles.role can only be changed by an administrator'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.email IS DISTINCT FROM OLD.email THEN
    RAISE EXCEPTION 'profiles.email is mirrored from auth.users and cannot be changed directly'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'profiles.created_at is immutable'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;


--
-- Name: update_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: announcements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.announcements (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id character varying,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: assignment_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assignment_submissions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    assignment_id uuid NOT NULL,
    student_id uuid NOT NULL,
    content text,
    file_url text,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    status character varying(20) DEFAULT 'submitted'::character varying NOT NULL,
    grade integer,
    feedback text,
    graded_by uuid,
    graded_at timestamp with time zone,
    CONSTRAINT assignment_submissions_grade_nonneg CHECK (((grade IS NULL) OR (grade >= 0))),
    CONSTRAINT assignment_submissions_status_check CHECK (((status)::text = ANY (ARRAY[('submitted'::character varying)::text, ('graded'::character varying)::text, ('returned'::character varying)::text])))
);


--
-- Name: assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assignments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    chapter_id character varying NOT NULL,
    max_score integer DEFAULT 100 NOT NULL,
    due_date timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT assignments_max_score_positive CHECK ((max_score > 0))
);


--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    action character varying(50) NOT NULL,
    resource_type character varying(50) NOT NULL,
    resource_id text NOT NULL,
    details jsonb,
    ip_address character varying(45),
    user_agent character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: certificates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.certificates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    course_id character varying,
    issued_at timestamp with time zone,
    certificate_number character varying(50),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    requested_at timestamp with time zone DEFAULT now() NOT NULL,
    teacher_approved_at timestamp with time zone,
    teacher_approved_by uuid,
    admin_approved_at timestamp with time zone,
    admin_approved_by uuid,
    cohort_id uuid,
    archived_course_title text,
    CONSTRAINT certificates_status_check CHECK (((status)::text = ANY (ARRAY[('pending'::character varying)::text, ('teacher_approved'::character varying)::text, ('approved'::character varying)::text, ('rejected'::character varying)::text])))
);


--
-- Name: chapter_blocks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chapter_blocks (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    chapter_id character varying NOT NULL,
    block_type character varying(20) NOT NULL,
    order_index integer DEFAULT 0 NOT NULL,
    quiz_id uuid,
    assignment_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    file_bucket character varying(50),
    file_path text,
    file_name character varying(255),
    CONSTRAINT chapter_blocks_block_type_check CHECK (((block_type)::text = ANY (ARRAY[('text'::character varying)::text, ('quiz'::character varying)::text, ('assignment'::character varying)::text, ('file'::character varying)::text])))
);


--
-- Name: chapter_progress; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chapter_progress (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    chapter_id character varying NOT NULL,
    completed_at timestamp with time zone DEFAULT now(),
    completed_by uuid,
    completion_type character varying(20) DEFAULT 'self'::character varying NOT NULL,
    completed boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chapter_progress_completion_type_check CHECK (((completion_type)::text = ANY (ARRAY[('self'::character varying)::text, ('teacher'::character varying)::text, ('quiz'::character varying)::text])))
);


--
-- Name: chapters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chapters (
    id character varying NOT NULL,
    module_id character varying NOT NULL,
    title character varying NOT NULL,
    order_index integer DEFAULT 0 NOT NULL,
    chapter_type character varying(20) DEFAULT 'reading'::character varying NOT NULL,
    requires_completion boolean DEFAULT false NOT NULL,
    is_locked boolean DEFAULT false NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT chapters_chapter_type_check CHECK (((chapter_type)::text = ANY (ARRAY[('reading'::character varying)::text, ('quiz'::character varying)::text, ('exam'::character varying)::text, ('assignment'::character varying)::text])))
);


--
-- Name: cohort_courses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cohort_courses (
    cohort_id uuid NOT NULL,
    course_id text NOT NULL,
    added_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cohorts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cohorts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    start_date timestamp with time zone NOT NULL,
    end_date timestamp with time zone NOT NULL,
    enrollment_start timestamp with time zone,
    enrollment_end timestamp with time zone,
    status character varying(20) DEFAULT 'upcoming'::character varying NOT NULL,
    max_students integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_by uuid,
    CONSTRAINT cohorts_status_check CHECK (((status)::text = ANY (ARRAY[('upcoming'::character varying)::text, ('active'::character varying)::text, ('completed'::character varying)::text, ('archived'::character varying)::text])))
);


--
-- Name: content_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.content_versions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    field text NOT NULL,
    locale text NOT NULL,
    text text NOT NULL,
    origin text NOT NULL,
    status text DEFAULT 'ok'::text NOT NULL,
    source_hash text,
    source_locale text,
    source_version_id uuid,
    authored_by uuid,
    attempts integer DEFAULT 0 NOT NULL,
    superseded_by uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT content_versions_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT content_versions_origin_check CHECK ((origin = ANY (ARRAY['human'::text, 'mt'::text]))),
    CONSTRAINT content_versions_status_check CHECK ((status = ANY (ARRAY['ok'::text, 'failed'::text, 'failed_permanent'::text])))
);


--
-- Name: course_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.course_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id character varying NOT NULL,
    event_type character varying(30) DEFAULT 'other'::character varying NOT NULL,
    event_date timestamp with time zone NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: course_prerequisites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.course_prerequisites (
    course_id character varying NOT NULL,
    prerequisite_course_id character varying NOT NULL,
    CONSTRAINT course_prerequisites_check CHECK (((course_id)::text <> (prerequisite_course_id)::text))
);


--
-- Name: course_reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.course_reviews (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    course_id character varying NOT NULL,
    rating integer NOT NULL,
    comment text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT course_reviews_rating_check CHECK (((rating >= 1) AND (rating <= 5)))
);


--
-- Name: courses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.courses (
    id character varying NOT NULL,
    image_url character varying,
    created_by uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    status text DEFAULT 'draft'::text NOT NULL,
    enrollment_start timestamp with time zone,
    enrollment_end timestamp with time zone,
    quiz_weight integer DEFAULT 30 NOT NULL,
    assignment_weight integer DEFAULT 50 NOT NULL,
    participation_weight integer DEFAULT 20 NOT NULL,
    deleted_at timestamp with time zone,
    source_locale character varying(8) DEFAULT 'ru'::character varying NOT NULL,
    access_mode text DEFAULT 'public'::text NOT NULL,
    CONSTRAINT chk_courses_status CHECK ((status = ANY (ARRAY['draft'::text, 'published'::text]))),
    CONSTRAINT courses_access_mode_check CHECK ((access_mode = ANY (ARRAY['public'::text, 'institute'::text]))),
    CONSTRAINT courses_source_locale_check CHECK (((source_locale)::text = ANY (ARRAY[('ru'::character varying)::text, ('en'::character varying)::text])))
);


--
-- Name: daily_challenge_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_challenge_attempts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    question_id uuid NOT NULL,
    challenge_date date NOT NULL,
    is_archive boolean DEFAULT false NOT NULL,
    selected_option_id uuid,
    is_correct boolean NOT NULL,
    streak_after integer,
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT daily_challenge_attempts_check CHECK (((NOT is_archive) OR (streak_after IS NULL)))
);


--
-- Name: daily_challenge_options; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_challenge_options (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    question_id uuid NOT NULL,
    is_correct boolean DEFAULT false NOT NULL,
    order_index integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT daily_challenge_options_order_index_check CHECK (((order_index >= 0) AND (order_index <= 5)))
);


--
-- Name: daily_challenge_pilot_reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_challenge_pilot_reviews (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    question_id uuid NOT NULL,
    reviewer_id uuid NOT NULL,
    answered_correctly boolean NOT NULL,
    engagement_rating integer NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT daily_challenge_pilot_reviews_engagement_rating_check CHECK (((engagement_rating >= 1) AND (engagement_rating <= 5)))
);


--
-- Name: daily_challenge_question_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_challenge_question_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    question_id uuid,
    event_type text NOT NULL,
    generation_run_id uuid,
    actor_id uuid,
    details jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT daily_challenge_question_events_event_type_check CHECK ((event_type = ANY (ARRAY['status_change'::text, 'rejected'::text, 'published'::text, 'scheduled'::text, 'unscheduled'::text, 'ai_generated'::text, 'ai_critique'::text, 'ai_synthesis'::text, 'scripture_validated'::text, 'doctrinally_reviewed'::text, 'bilingually_reviewed'::text, 'pilot_summary'::text]))),
    CONSTRAINT dc_q_events_type_check CHECK ((event_type = ANY (ARRAY['status_change'::text, 'rejected'::text, 'published'::text, 'scheduled'::text, 'unscheduled'::text, 'ai_generated'::text, 'ai_critique'::text, 'ai_synthesis'::text, 'scripture_validated'::text, 'doctrinally_reviewed'::text, 'bilingually_reviewed'::text, 'pilot_summary'::text, 'bilingual_edit'::text])))
);


--
-- Name: daily_challenge_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_challenge_questions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    question_type text NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    rejected boolean DEFAULT false NOT NULL,
    rejection_reason text,
    rejected_by uuid,
    rejected_at timestamp with time zone,
    published_at timestamp with time zone,
    published_by uuid,
    created_by uuid,
    bible_book text NOT NULL,
    bible_chapter integer NOT NULL,
    bible_verse_from integer,
    bible_verse_to integer,
    category text,
    source_locale text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT daily_challenge_questions_bible_chapter_check CHECK ((bible_chapter > 0)),
    CONSTRAINT daily_challenge_questions_bible_verse_from_check CHECK (((bible_verse_from IS NULL) OR (bible_verse_from > 0))),
    CONSTRAINT daily_challenge_questions_check CHECK (((bible_verse_to IS NULL) OR ((bible_verse_from IS NOT NULL) AND (bible_verse_to >= bible_verse_from)))),
    CONSTRAINT daily_challenge_questions_question_type_check CHECK ((question_type = ANY (ARRAY['multiple_choice'::text, 'true_false'::text]))),
    CONSTRAINT daily_challenge_questions_status_check CHECK ((status = ANY (ARRAY['draft'::text, 'scripture_validated'::text, 'doctrinally_reviewed'::text, 'bilingually_reviewed'::text, 'pilot_passed'::text, 'published'::text, 'archived'::text])))
);


--
-- Name: daily_challenge_schedule; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_challenge_schedule (
    challenge_date date NOT NULL,
    question_id uuid NOT NULL,
    scheduled_by uuid,
    scheduled_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: daily_challenge_streaks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_challenge_streaks (
    user_id uuid NOT NULL,
    current_streak integer DEFAULT 0 NOT NULL,
    longest_streak integer DEFAULT 0 NOT NULL,
    last_engaged_date date,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT daily_challenge_streaks_current_streak_check CHECK ((current_streak >= 0)),
    CONSTRAINT daily_challenge_streaks_longest_streak_check CHECK ((longest_streak >= 0))
);


--
-- Name: enrollments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.enrollments (
    id character varying NOT NULL,
    user_id uuid NOT NULL,
    course_id character varying NOT NULL,
    enrolled_at timestamp with time zone DEFAULT now(),
    progress integer DEFAULT 0 NOT NULL,
    cohort_id uuid,
    CONSTRAINT enrollments_progress_range CHECK (((progress >= 0) AND (progress <= 100)))
);


--
-- Name: modules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.modules (
    id character varying NOT NULL,
    course_id character varying NOT NULL,
    order_index integer DEFAULT 0 NOT NULL,
    due_date timestamp with time zone,
    deleted_at timestamp with time zone
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    message text NOT NULL,
    link character varying(500),
    is_read boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    meta jsonb
);


--
-- Name: profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.profiles (
    id uuid NOT NULL,
    email text NOT NULL,
    full_name text,
    role text DEFAULT 'student'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone,
    avatar_url text,
    preferred_locale character varying(8) DEFAULT 'ru'::character varying NOT NULL,
    calendar_ical_min_iat bigint,
    CONSTRAINT chk_profiles_role CHECK ((role = ANY (ARRAY['admin'::text, 'teacher'::text, 'pending_teacher'::text, 'student'::text]))),
    CONSTRAINT profiles_preferred_locale_check CHECK (((preferred_locale)::text = ANY (ARRAY[('ru'::character varying)::text, ('en'::character varying)::text])))
)
WITH (autovacuum_vacuum_threshold='25', autovacuum_analyze_threshold='25');


--
-- Name: quiz_answers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quiz_answers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    attempt_id uuid NOT NULL,
    question_id uuid NOT NULL,
    selected_option_id uuid,
    text_answer text,
    is_correct boolean,
    points_earned integer DEFAULT 0 NOT NULL,
    grader_comment text,
    graded_at timestamp with time zone
)
WITH (autovacuum_vacuum_threshold='25', autovacuum_analyze_threshold='25');


--
-- Name: quiz_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quiz_attempts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    quiz_id uuid NOT NULL,
    user_id uuid NOT NULL,
    score integer,
    max_score integer,
    passed boolean,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT quiz_attempts_max_score_nonneg CHECK (((max_score IS NULL) OR (max_score >= 0))),
    CONSTRAINT quiz_attempts_score_nonneg CHECK (((score IS NULL) OR (score >= 0)))
)
WITH (autovacuum_vacuum_threshold='10', autovacuum_analyze_threshold='10');


--
-- Name: quiz_extra_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quiz_extra_attempts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    quiz_id uuid NOT NULL,
    user_id uuid NOT NULL,
    extra_attempts integer DEFAULT 1 NOT NULL,
    granted_by uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: quiz_options; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quiz_options (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    question_id uuid NOT NULL,
    is_correct boolean DEFAULT false NOT NULL,
    order_index integer DEFAULT 0 NOT NULL
);


--
-- Name: quiz_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quiz_questions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    quiz_id uuid NOT NULL,
    question_type character varying(20) DEFAULT 'multiple_choice'::character varying NOT NULL,
    order_index integer DEFAULT 0 NOT NULL,
    points integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    min_words integer,
    CONSTRAINT quiz_questions_min_words_nonneg CHECK (((min_words IS NULL) OR (min_words >= 0))),
    CONSTRAINT quiz_questions_points_range CHECK (((points >= 1) AND (points <= 100))),
    CONSTRAINT quiz_questions_question_type_check CHECK (((question_type)::text = ANY (ARRAY[('multiple_choice'::character varying)::text, ('true_false'::character varying)::text, ('short_answer'::character varying)::text, ('essay'::character varying)::text])))
);


--
-- Name: quizzes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quizzes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    chapter_id character varying NOT NULL,
    passing_score integer DEFAULT 70 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    quiz_type character varying(20) DEFAULT 'quiz'::character varying NOT NULL,
    max_attempts integer,
    CONSTRAINT quizzes_max_attempts_positive CHECK (((max_attempts IS NULL) OR (max_attempts > 0))),
    CONSTRAINT quizzes_passing_score_range CHECK (((passing_score >= 0) AND (passing_score <= 100))),
    CONSTRAINT quizzes_quiz_type_check CHECK (((quiz_type)::text = ANY (ARRAY[('quiz'::character varying)::text, ('exam'::character varying)::text])))
);


--
-- Name: student_grades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.student_grades (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    student_id uuid NOT NULL,
    course_id character varying NOT NULL,
    grade character varying(10),
    comment text,
    graded_by uuid,
    graded_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    cohort_id uuid
);


--
-- Name: translation_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.translation_jobs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    course_id text NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    enqueued_at timestamp with time zone DEFAULT now() NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    attempts integer DEFAULT 0 NOT NULL,
    last_error text,
    requested_by uuid,
    CONSTRAINT translation_jobs_attempts_check CHECK ((attempts >= 0)),
    CONSTRAINT translation_jobs_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'processing'::text, 'done'::text, 'failed'::text, 'failed_permanent'::text])))
);


--
-- Name: announcements announcements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT announcements_pkey PRIMARY KEY (id);


--
-- Name: assignment_submissions assignment_submissions_assignment_id_student_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignment_submissions
    ADD CONSTRAINT assignment_submissions_assignment_id_student_id_key UNIQUE (assignment_id, student_id);


--
-- Name: assignment_submissions assignment_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignment_submissions
    ADD CONSTRAINT assignment_submissions_pkey PRIMARY KEY (id);


--
-- Name: assignments assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignments
    ADD CONSTRAINT assignments_pkey PRIMARY KEY (id);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: certificates certificates_certificate_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_certificate_number_key UNIQUE (certificate_number);


--
-- Name: certificates certificates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_pkey PRIMARY KEY (id);


--
-- Name: certificates certificates_user_course_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_user_course_unique UNIQUE (user_id, course_id);


--
-- Name: chapter_blocks chapter_blocks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapter_blocks
    ADD CONSTRAINT chapter_blocks_pkey PRIMARY KEY (id);


--
-- Name: chapter_progress chapter_progress_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapter_progress
    ADD CONSTRAINT chapter_progress_pkey PRIMARY KEY (id);


--
-- Name: chapter_progress chapter_progress_user_id_chapter_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapter_progress
    ADD CONSTRAINT chapter_progress_user_id_chapter_id_key UNIQUE (user_id, chapter_id);


--
-- Name: chapters chapters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapters
    ADD CONSTRAINT chapters_pkey PRIMARY KEY (id);


--
-- Name: cohort_courses cohort_courses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cohort_courses
    ADD CONSTRAINT cohort_courses_pkey PRIMARY KEY (cohort_id, course_id);


--
-- Name: cohorts cohorts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cohorts
    ADD CONSTRAINT cohorts_pkey PRIMARY KEY (id);


--
-- Name: content_versions content_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_versions
    ADD CONSTRAINT content_versions_pkey PRIMARY KEY (id);


--
-- Name: course_events course_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_events
    ADD CONSTRAINT course_events_pkey PRIMARY KEY (id);


--
-- Name: course_prerequisites course_prerequisites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_prerequisites
    ADD CONSTRAINT course_prerequisites_pkey PRIMARY KEY (course_id, prerequisite_course_id);


--
-- Name: course_reviews course_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_reviews
    ADD CONSTRAINT course_reviews_pkey PRIMARY KEY (id);


--
-- Name: course_reviews course_reviews_user_id_course_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_reviews
    ADD CONSTRAINT course_reviews_user_id_course_id_key UNIQUE (user_id, course_id);


--
-- Name: courses courses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.courses
    ADD CONSTRAINT courses_pkey PRIMARY KEY (id);


--
-- Name: daily_challenge_attempts daily_challenge_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_attempts
    ADD CONSTRAINT daily_challenge_attempts_pkey PRIMARY KEY (id);


--
-- Name: daily_challenge_options daily_challenge_options_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_options
    ADD CONSTRAINT daily_challenge_options_pkey PRIMARY KEY (id);


--
-- Name: daily_challenge_pilot_reviews daily_challenge_pilot_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_pilot_reviews
    ADD CONSTRAINT daily_challenge_pilot_reviews_pkey PRIMARY KEY (id);


--
-- Name: daily_challenge_pilot_reviews daily_challenge_pilot_reviews_question_id_reviewer_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_pilot_reviews
    ADD CONSTRAINT daily_challenge_pilot_reviews_question_id_reviewer_id_key UNIQUE (question_id, reviewer_id);


--
-- Name: daily_challenge_question_events daily_challenge_question_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_question_events
    ADD CONSTRAINT daily_challenge_question_events_pkey PRIMARY KEY (id);


--
-- Name: daily_challenge_questions daily_challenge_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_questions
    ADD CONSTRAINT daily_challenge_questions_pkey PRIMARY KEY (id);


--
-- Name: daily_challenge_schedule daily_challenge_schedule_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_schedule
    ADD CONSTRAINT daily_challenge_schedule_pkey PRIMARY KEY (challenge_date);


--
-- Name: daily_challenge_streaks daily_challenge_streaks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_streaks
    ADD CONSTRAINT daily_challenge_streaks_pkey PRIMARY KEY (user_id);


--
-- Name: enrollments enrollments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_pkey PRIMARY KEY (id);


--
-- Name: modules modules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: profiles profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT profiles_pkey PRIMARY KEY (id);


--
-- Name: quiz_answers quiz_answers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_answers
    ADD CONSTRAINT quiz_answers_pkey PRIMARY KEY (id);


--
-- Name: quiz_attempts quiz_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_attempts
    ADD CONSTRAINT quiz_attempts_pkey PRIMARY KEY (id);


--
-- Name: quiz_extra_attempts quiz_extra_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_extra_attempts
    ADD CONSTRAINT quiz_extra_attempts_pkey PRIMARY KEY (id);


--
-- Name: quiz_options quiz_options_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_options
    ADD CONSTRAINT quiz_options_pkey PRIMARY KEY (id);


--
-- Name: quiz_questions quiz_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_questions
    ADD CONSTRAINT quiz_questions_pkey PRIMARY KEY (id);


--
-- Name: quizzes quizzes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quizzes
    ADD CONSTRAINT quizzes_pkey PRIMARY KEY (id);


--
-- Name: student_grades student_grades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_grades
    ADD CONSTRAINT student_grades_pkey PRIMARY KEY (id);


--
-- Name: student_grades student_grades_student_id_course_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_grades
    ADD CONSTRAINT student_grades_student_id_course_id_key UNIQUE (student_id, course_id);


--
-- Name: translation_jobs translation_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.translation_jobs
    ADD CONSTRAINT translation_jobs_pkey PRIMARY KEY (id);


--
-- Name: idx_profiles_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_profiles_email ON public.profiles USING btree (email);


--
-- Name: idx_profiles_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_profiles_role ON public.profiles USING btree (role);


--
-- Name: idx_quiz_attempts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quiz_attempts_user_id ON public.quiz_attempts USING btree (user_id);


--
-- Name: idx_quiz_options_question_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quiz_options_question_id ON public.quiz_options USING btree (question_id);


--
-- Name: idx_quiz_questions_quiz_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quiz_questions_quiz_id ON public.quiz_questions USING btree (quiz_id);


--
-- Name: idx_student_grades_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_student_grades_course_id ON public.student_grades USING btree (course_id);


--
-- Name: idx_submissions_student_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_submissions_student_id ON public.assignment_submissions USING btree (student_id);


--
-- Name: ix_announcements_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_announcements_course_id ON public.announcements USING btree (course_id);


--
-- Name: ix_announcements_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_announcements_created_by ON public.announcements USING btree (created_by);


--
-- Name: ix_assignment_submissions_graded_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assignment_submissions_graded_by ON public.assignment_submissions USING btree (graded_by);


--
-- Name: ix_assignments_chapter_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_assignments_chapter_id ON public.assignments USING btree (chapter_id);


--
-- Name: ix_audit_logs_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_action ON public.audit_logs USING btree (action);


--
-- Name: ix_audit_logs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_created_at ON public.audit_logs USING btree (created_at);


--
-- Name: ix_audit_logs_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_user_id ON public.audit_logs USING btree (user_id);


--
-- Name: ix_certificates_admin_approved_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_certificates_admin_approved_by ON public.certificates USING btree (admin_approved_by) WHERE (admin_approved_by IS NOT NULL);


--
-- Name: ix_certificates_cohort_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_certificates_cohort_id ON public.certificates USING btree (cohort_id) WHERE (cohort_id IS NOT NULL);


--
-- Name: ix_certificates_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_certificates_course_id ON public.certificates USING btree (course_id) WHERE (course_id IS NOT NULL);


--
-- Name: ix_certificates_teacher_approved_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_certificates_teacher_approved_by ON public.certificates USING btree (teacher_approved_by) WHERE (teacher_approved_by IS NOT NULL);


--
-- Name: ix_chapter_blocks_assignment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chapter_blocks_assignment_id ON public.chapter_blocks USING btree (assignment_id);


--
-- Name: ix_chapter_blocks_chapter_id_order; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chapter_blocks_chapter_id_order ON public.chapter_blocks USING btree (chapter_id, order_index);


--
-- Name: ix_chapter_blocks_quiz_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chapter_blocks_quiz_id ON public.chapter_blocks USING btree (quiz_id);


--
-- Name: ix_chapter_progress_chapter_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chapter_progress_chapter_id ON public.chapter_progress USING btree (chapter_id);


--
-- Name: ix_chapter_progress_completed_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chapter_progress_completed_by ON public.chapter_progress USING btree (completed_by) WHERE (completed_by IS NOT NULL);


--
-- Name: ix_chapters_module_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chapters_module_id ON public.chapters USING btree (module_id);


--
-- Name: ix_cohort_courses_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cohort_courses_course_id ON public.cohort_courses USING btree (course_id);


--
-- Name: ix_cohorts_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_cohorts_created_by ON public.cohorts USING btree (created_by);


--
-- Name: ix_content_versions_active_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_versions_active_lookup ON public.content_versions USING btree (entity_type, entity_id, locale) WHERE ((superseded_by IS NULL) AND (status = 'ok'::text));


--
-- Name: ix_content_versions_authored_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_versions_authored_by ON public.content_versions USING btree (authored_by) WHERE (authored_by IS NOT NULL);


--
-- Name: ix_content_versions_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_versions_entity ON public.content_versions USING btree (entity_type, entity_id);


--
-- Name: ix_content_versions_source_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_versions_source_version ON public.content_versions USING btree (source_version_id) WHERE (source_version_id IS NOT NULL);


--
-- Name: ix_content_versions_superseded_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_content_versions_superseded_by ON public.content_versions USING btree (superseded_by) WHERE (superseded_by IS NOT NULL);


--
-- Name: ix_course_events_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_course_events_course_id ON public.course_events USING btree (course_id);


--
-- Name: ix_course_prerequisites_prerequisite_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_course_prerequisites_prerequisite_course_id ON public.course_prerequisites USING btree (prerequisite_course_id);


--
-- Name: ix_course_reviews_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_course_reviews_course_id ON public.course_reviews USING btree (course_id);


--
-- Name: ix_courses_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_courses_created_by ON public.courses USING btree (created_by);


--
-- Name: ix_courses_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_courses_deleted_at ON public.courses USING btree (deleted_at) WHERE (deleted_at IS NOT NULL);


--
-- Name: ix_dc_attempts_question; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_attempts_question ON public.daily_challenge_attempts USING btree (question_id);


--
-- Name: ix_dc_attempts_selected_option_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_attempts_selected_option_id ON public.daily_challenge_attempts USING btree (selected_option_id) WHERE (selected_option_id IS NOT NULL);


--
-- Name: ix_dc_attempts_user_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_attempts_user_date ON public.daily_challenge_attempts USING btree (user_id, challenge_date DESC);


--
-- Name: ix_dc_options_question; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_options_question ON public.daily_challenge_options USING btree (question_id, order_index);


--
-- Name: ix_dc_pilot_reviews_question; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_pilot_reviews_question ON public.daily_challenge_pilot_reviews USING btree (question_id);


--
-- Name: ix_dc_pilot_reviews_reviewer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_pilot_reviews_reviewer ON public.daily_challenge_pilot_reviews USING btree (reviewer_id);


--
-- Name: ix_dc_q_events_actor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_q_events_actor_id ON public.daily_challenge_question_events USING btree (actor_id) WHERE (actor_id IS NOT NULL);


--
-- Name: ix_dc_q_events_generation_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_q_events_generation_run ON public.daily_challenge_question_events USING btree (generation_run_id, created_at) WHERE (generation_run_id IS NOT NULL);


--
-- Name: ix_dc_q_events_question_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_q_events_question_created ON public.daily_challenge_question_events USING btree (question_id, created_at);


--
-- Name: ix_dc_questions_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_questions_created_by ON public.daily_challenge_questions USING btree (created_by) WHERE (created_by IS NOT NULL);


--
-- Name: ix_dc_questions_publishable; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_questions_publishable ON public.daily_challenge_questions USING btree (published_at) WHERE ((status = 'published'::text) AND (rejected = false));


--
-- Name: ix_dc_questions_published_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_questions_published_by ON public.daily_challenge_questions USING btree (published_by) WHERE (published_by IS NOT NULL);


--
-- Name: ix_dc_questions_rejected_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_questions_rejected_by ON public.daily_challenge_questions USING btree (rejected_by) WHERE (rejected_by IS NOT NULL);


--
-- Name: ix_dc_questions_scripture; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_questions_scripture ON public.daily_challenge_questions USING btree (bible_book, bible_chapter, bible_verse_from);


--
-- Name: ix_dc_questions_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_questions_status_created ON public.daily_challenge_questions USING btree (status, created_at DESC) WHERE ((rejected = false) AND (status <> 'archived'::text));


--
-- Name: ix_dc_schedule_question; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_schedule_question ON public.daily_challenge_schedule USING btree (question_id);


--
-- Name: ix_dc_schedule_scheduled_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_schedule_scheduled_by ON public.daily_challenge_schedule USING btree (scheduled_by) WHERE (scheduled_by IS NOT NULL);


--
-- Name: ix_dc_streaks_last_engaged; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dc_streaks_last_engaged ON public.daily_challenge_streaks USING btree (last_engaged_date) WHERE (current_streak >= 1);


--
-- Name: ix_enrollments_cohort_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_enrollments_cohort_id ON public.enrollments USING btree (cohort_id) WHERE (cohort_id IS NOT NULL);


--
-- Name: ix_enrollments_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_enrollments_course_id ON public.enrollments USING btree (course_id);


--
-- Name: ix_enrollments_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_enrollments_user_id ON public.enrollments USING btree (user_id);


--
-- Name: ix_modules_course_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_modules_course_id ON public.modules USING btree (course_id);


--
-- Name: ix_notifications_user_id_is_read; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_user_id_is_read ON public.notifications USING btree (user_id, is_read);


--
-- Name: ix_quiz_answers_attempt_question; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quiz_answers_attempt_question ON public.quiz_answers USING btree (attempt_id, question_id);


--
-- Name: ix_quiz_answers_graded_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quiz_answers_graded_at ON public.quiz_answers USING btree (graded_at);


--
-- Name: ix_quiz_answers_question_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quiz_answers_question_id ON public.quiz_answers USING btree (question_id);


--
-- Name: ix_quiz_answers_selected_option_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quiz_answers_selected_option_id ON public.quiz_answers USING btree (selected_option_id);


--
-- Name: ix_quiz_attempts_quiz_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quiz_attempts_quiz_id ON public.quiz_attempts USING btree (quiz_id);


--
-- Name: ix_quiz_extra_attempts_quiz_user; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_quiz_extra_attempts_quiz_user ON public.quiz_extra_attempts USING btree (quiz_id, user_id);


--
-- Name: ix_quiz_extra_attempts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quiz_extra_attempts_user_id ON public.quiz_extra_attempts USING btree (user_id);


--
-- Name: ix_quizzes_chapter_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_quizzes_chapter_id ON public.quizzes USING btree (chapter_id);


--
-- Name: ix_student_grades_cohort_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_student_grades_cohort_id ON public.student_grades USING btree (cohort_id) WHERE (cohort_id IS NOT NULL);


--
-- Name: ix_student_grades_graded_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_student_grades_graded_by ON public.student_grades USING btree (graded_by);


--
-- Name: ix_translation_jobs_course; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_translation_jobs_course ON public.translation_jobs USING btree (course_id, enqueued_at DESC);


--
-- Name: ix_translation_jobs_processing; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_translation_jobs_processing ON public.translation_jobs USING btree (started_at) WHERE (status = 'processing'::text);


--
-- Name: ix_translation_jobs_queued; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_translation_jobs_queued ON public.translation_jobs USING btree (enqueued_at) WHERE (status = 'queued'::text);


--
-- Name: ix_translation_jobs_requested_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_translation_jobs_requested_by ON public.translation_jobs USING btree (requested_by) WHERE (requested_by IS NOT NULL);


--
-- Name: student_grades_student_course_cohort_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX student_grades_student_course_cohort_unique ON public.student_grades USING btree (student_id, course_id, cohort_id) NULLS NOT DISTINCT;


--
-- Name: uniq_content_versions_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uniq_content_versions_active ON public.content_versions USING btree (entity_type, entity_id, field, locale) WHERE (superseded_by IS NULL);


--
-- Name: uniq_dc_attempts_live_per_day; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uniq_dc_attempts_live_per_day ON public.daily_challenge_attempts USING btree (user_id, challenge_date) WHERE (is_archive = false);


--
-- Name: uq_enrollment_user_course_cohort; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_enrollment_user_course_cohort ON public.enrollments USING btree (user_id, course_id, COALESCE(cohort_id, '00000000-0000-0000-0000-000000000000'::uuid));


--
-- Name: content_versions content_versions_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER content_versions_updated_at BEFORE UPDATE ON public.content_versions FOR EACH ROW EXECUTE FUNCTION public.content_versions_set_updated_at();


--
-- Name: daily_challenge_schedule dc_schedule_publishable_guard; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER dc_schedule_publishable_guard BEFORE INSERT OR UPDATE OF question_id ON public.daily_challenge_schedule FOR EACH ROW EXECUTE FUNCTION public.dc_schedule_assert_publishable();


--
-- Name: announcements trg_announcements_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_announcements_updated_at BEFORE UPDATE ON public.announcements FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: assignments trg_assignments_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_assignments_updated_at BEFORE UPDATE ON public.assignments FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: chapter_blocks trg_chapter_blocks_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_chapter_blocks_updated_at BEFORE UPDATE ON public.chapter_blocks FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: cohorts trg_cohorts_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_cohorts_updated_at BEFORE UPDATE ON public.cohorts FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: courses trg_courses_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_courses_updated_at BEFORE UPDATE ON public.courses FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: profiles trg_profiles_protect_immutable_fields; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_profiles_protect_immutable_fields BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.profiles_protect_immutable_fields();


--
-- Name: profiles trg_profiles_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_profiles_updated_at BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: quizzes trg_quizzes_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_quizzes_updated_at BEFORE UPDATE ON public.quizzes FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: course_reviews trg_reviews_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_reviews_updated_at BEFORE UPDATE ON public.course_reviews FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: student_grades trg_student_grades_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_student_grades_updated_at BEFORE UPDATE ON public.student_grades FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();


--
-- Name: announcements announcements_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT announcements_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: announcements announcements_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.announcements
    ADD CONSTRAINT announcements_created_by_fkey FOREIGN KEY (created_by) REFERENCES auth.users(id);


--
-- Name: assignment_submissions assignment_submissions_assignment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignment_submissions
    ADD CONSTRAINT assignment_submissions_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.assignments(id) ON DELETE CASCADE;


--
-- Name: assignment_submissions assignment_submissions_graded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignment_submissions
    ADD CONSTRAINT assignment_submissions_graded_by_fkey FOREIGN KEY (graded_by) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: assignment_submissions assignment_submissions_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignment_submissions
    ADD CONSTRAINT assignment_submissions_student_id_fkey FOREIGN KEY (student_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: assignments assignments_chapter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assignments
    ADD CONSTRAINT assignments_chapter_id_fkey FOREIGN KEY (chapter_id) REFERENCES public.chapters(id) ON DELETE CASCADE;


--
-- Name: certificates certificates_admin_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_admin_approved_by_fkey FOREIGN KEY (admin_approved_by) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: certificates certificates_cohort_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_cohort_id_fkey FOREIGN KEY (cohort_id) REFERENCES public.cohorts(id) ON DELETE SET NULL;


--
-- Name: certificates certificates_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE SET NULL;


--
-- Name: certificates certificates_teacher_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_teacher_approved_by_fkey FOREIGN KEY (teacher_approved_by) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: certificates certificates_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: chapter_blocks chapter_blocks_assignment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapter_blocks
    ADD CONSTRAINT chapter_blocks_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.assignments(id) ON DELETE SET NULL;


--
-- Name: chapter_blocks chapter_blocks_chapter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapter_blocks
    ADD CONSTRAINT chapter_blocks_chapter_id_fkey FOREIGN KEY (chapter_id) REFERENCES public.chapters(id) ON DELETE CASCADE;


--
-- Name: chapter_blocks chapter_blocks_quiz_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapter_blocks
    ADD CONSTRAINT chapter_blocks_quiz_id_fkey FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE SET NULL;


--
-- Name: chapter_progress chapter_progress_chapter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapter_progress
    ADD CONSTRAINT chapter_progress_chapter_id_fkey FOREIGN KEY (chapter_id) REFERENCES public.chapters(id) ON DELETE CASCADE;


--
-- Name: chapter_progress chapter_progress_completed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapter_progress
    ADD CONSTRAINT chapter_progress_completed_by_fkey FOREIGN KEY (completed_by) REFERENCES auth.users(id);


--
-- Name: chapter_progress chapter_progress_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapter_progress
    ADD CONSTRAINT chapter_progress_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: chapters chapters_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chapters
    ADD CONSTRAINT chapters_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.modules(id) ON DELETE CASCADE;


--
-- Name: cohort_courses cohort_courses_cohort_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cohort_courses
    ADD CONSTRAINT cohort_courses_cohort_id_fkey FOREIGN KEY (cohort_id) REFERENCES public.cohorts(id) ON DELETE CASCADE;


--
-- Name: cohort_courses cohort_courses_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cohort_courses
    ADD CONSTRAINT cohort_courses_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: cohorts cohorts_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cohorts
    ADD CONSTRAINT cohorts_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: content_versions content_versions_authored_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_versions
    ADD CONSTRAINT content_versions_authored_by_fkey FOREIGN KEY (authored_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: content_versions content_versions_source_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_versions
    ADD CONSTRAINT content_versions_source_version_id_fkey FOREIGN KEY (source_version_id) REFERENCES public.content_versions(id) ON DELETE SET NULL;


--
-- Name: content_versions content_versions_superseded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.content_versions
    ADD CONSTRAINT content_versions_superseded_by_fkey FOREIGN KEY (superseded_by) REFERENCES public.content_versions(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;


--
-- Name: course_events course_events_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_events
    ADD CONSTRAINT course_events_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: course_prerequisites course_prerequisites_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_prerequisites
    ADD CONSTRAINT course_prerequisites_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: course_prerequisites course_prerequisites_prerequisite_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_prerequisites
    ADD CONSTRAINT course_prerequisites_prerequisite_course_id_fkey FOREIGN KEY (prerequisite_course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: course_reviews course_reviews_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_reviews
    ADD CONSTRAINT course_reviews_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: course_reviews course_reviews_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.course_reviews
    ADD CONSTRAINT course_reviews_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: courses courses_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.courses
    ADD CONSTRAINT courses_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: daily_challenge_attempts daily_challenge_attempts_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_attempts
    ADD CONSTRAINT daily_challenge_attempts_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.daily_challenge_questions(id) ON DELETE CASCADE;


--
-- Name: daily_challenge_attempts daily_challenge_attempts_selected_option_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_attempts
    ADD CONSTRAINT daily_challenge_attempts_selected_option_id_fkey FOREIGN KEY (selected_option_id) REFERENCES public.daily_challenge_options(id) ON DELETE SET NULL;


--
-- Name: daily_challenge_attempts daily_challenge_attempts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_attempts
    ADD CONSTRAINT daily_challenge_attempts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: daily_challenge_options daily_challenge_options_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_options
    ADD CONSTRAINT daily_challenge_options_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.daily_challenge_questions(id) ON DELETE CASCADE;


--
-- Name: daily_challenge_pilot_reviews daily_challenge_pilot_reviews_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_pilot_reviews
    ADD CONSTRAINT daily_challenge_pilot_reviews_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.daily_challenge_questions(id) ON DELETE CASCADE;


--
-- Name: daily_challenge_pilot_reviews daily_challenge_pilot_reviews_reviewer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_pilot_reviews
    ADD CONSTRAINT daily_challenge_pilot_reviews_reviewer_id_fkey FOREIGN KEY (reviewer_id) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: daily_challenge_question_events daily_challenge_question_events_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_question_events
    ADD CONSTRAINT daily_challenge_question_events_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: daily_challenge_question_events daily_challenge_question_events_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_question_events
    ADD CONSTRAINT daily_challenge_question_events_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.daily_challenge_questions(id) ON DELETE CASCADE;


--
-- Name: daily_challenge_questions daily_challenge_questions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_questions
    ADD CONSTRAINT daily_challenge_questions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: daily_challenge_questions daily_challenge_questions_published_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_questions
    ADD CONSTRAINT daily_challenge_questions_published_by_fkey FOREIGN KEY (published_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: daily_challenge_questions daily_challenge_questions_rejected_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_questions
    ADD CONSTRAINT daily_challenge_questions_rejected_by_fkey FOREIGN KEY (rejected_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: daily_challenge_schedule daily_challenge_schedule_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_schedule
    ADD CONSTRAINT daily_challenge_schedule_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.daily_challenge_questions(id) ON DELETE RESTRICT;


--
-- Name: daily_challenge_schedule daily_challenge_schedule_scheduled_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_schedule
    ADD CONSTRAINT daily_challenge_schedule_scheduled_by_fkey FOREIGN KEY (scheduled_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: daily_challenge_streaks daily_challenge_streaks_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_challenge_streaks
    ADD CONSTRAINT daily_challenge_streaks_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: enrollments enrollments_cohort_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_cohort_id_fkey FOREIGN KEY (cohort_id) REFERENCES public.cohorts(id) ON DELETE SET NULL;


--
-- Name: enrollments enrollments_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: enrollments enrollments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.enrollments
    ADD CONSTRAINT enrollments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: modules modules_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: profiles profiles_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.profiles
    ADD CONSTRAINT profiles_id_fkey FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: quiz_answers quiz_answers_attempt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_answers
    ADD CONSTRAINT quiz_answers_attempt_id_fkey FOREIGN KEY (attempt_id) REFERENCES public.quiz_attempts(id) ON DELETE CASCADE;


--
-- Name: quiz_answers quiz_answers_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_answers
    ADD CONSTRAINT quiz_answers_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.quiz_questions(id) ON DELETE CASCADE;


--
-- Name: quiz_answers quiz_answers_selected_option_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_answers
    ADD CONSTRAINT quiz_answers_selected_option_id_fkey FOREIGN KEY (selected_option_id) REFERENCES public.quiz_options(id) ON DELETE SET NULL;


--
-- Name: quiz_attempts quiz_attempts_quiz_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_attempts
    ADD CONSTRAINT quiz_attempts_quiz_id_fkey FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE CASCADE;


--
-- Name: quiz_attempts quiz_attempts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_attempts
    ADD CONSTRAINT quiz_attempts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: quiz_extra_attempts quiz_extra_attempts_quiz_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_extra_attempts
    ADD CONSTRAINT quiz_extra_attempts_quiz_id_fkey FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE CASCADE;


--
-- Name: quiz_extra_attempts quiz_extra_attempts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_extra_attempts
    ADD CONSTRAINT quiz_extra_attempts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE CASCADE;


--
-- Name: quiz_options quiz_options_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_options
    ADD CONSTRAINT quiz_options_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.quiz_questions(id) ON DELETE CASCADE;


--
-- Name: quiz_questions quiz_questions_quiz_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quiz_questions
    ADD CONSTRAINT quiz_questions_quiz_id_fkey FOREIGN KEY (quiz_id) REFERENCES public.quizzes(id) ON DELETE CASCADE;


--
-- Name: quizzes quizzes_chapter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quizzes
    ADD CONSTRAINT quizzes_chapter_id_fkey FOREIGN KEY (chapter_id) REFERENCES public.chapters(id) ON DELETE CASCADE;


--
-- Name: student_grades student_grades_cohort_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_grades
    ADD CONSTRAINT student_grades_cohort_id_fkey FOREIGN KEY (cohort_id) REFERENCES public.cohorts(id) ON DELETE SET NULL;


--
-- Name: student_grades student_grades_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_grades
    ADD CONSTRAINT student_grades_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: student_grades student_grades_graded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_grades
    ADD CONSTRAINT student_grades_graded_by_fkey FOREIGN KEY (graded_by) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: student_grades student_grades_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_grades
    ADD CONSTRAINT student_grades_student_id_fkey FOREIGN KEY (student_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: translation_jobs translation_jobs_course_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.translation_jobs
    ADD CONSTRAINT translation_jobs_course_id_fkey FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE CASCADE;


--
-- Name: translation_jobs translation_jobs_requested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.translation_jobs
    ADD CONSTRAINT translation_jobs_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES public.profiles(id) ON DELETE SET NULL;


--
-- Name: announcements; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.announcements ENABLE ROW LEVEL SECURITY;

--
-- Name: announcements announcements_select_authenticated; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY announcements_select_authenticated ON public.announcements FOR SELECT TO authenticated USING ((( SELECT auth.uid() AS uid) IS NOT NULL));


--
-- Name: assignment_submissions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.assignment_submissions ENABLE ROW LEVEL SECURITY;

--
-- Name: assignments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.assignments ENABLE ROW LEVEL SECURITY;

--
-- Name: assignments assignments_select_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY assignments_select_all ON public.assignments FOR SELECT TO authenticated USING ((( SELECT auth.uid() AS uid) IS NOT NULL));


--
-- Name: audit_logs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

--
-- Name: audit_logs audit_logs_select_admin; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY audit_logs_select_admin ON public.audit_logs FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = 'admin'::text)))));


--
-- Name: chapter_blocks blocks_select_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY blocks_select_all ON public.chapter_blocks FOR SELECT TO authenticated USING ((( SELECT auth.uid() AS uid) IS NOT NULL));


--
-- Name: certificates; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.certificates ENABLE ROW LEVEL SECURITY;

--
-- Name: certificates certificates_insert_request; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY certificates_insert_request ON public.certificates FOR INSERT TO authenticated WITH CHECK ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: certificates certificates_select_own_or_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY certificates_select_own_or_teacher ON public.certificates FOR SELECT TO authenticated USING (((user_id = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text])))))));


--
-- Name: chapter_blocks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.chapter_blocks ENABLE ROW LEVEL SECURITY;

--
-- Name: chapter_progress; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.chapter_progress ENABLE ROW LEVEL SECURITY;

--
-- Name: chapter_progress chapter_progress_delete_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY chapter_progress_delete_own ON public.chapter_progress FOR DELETE TO authenticated USING ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: chapter_progress chapter_progress_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY chapter_progress_insert_own ON public.chapter_progress FOR INSERT TO authenticated WITH CHECK ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: chapter_progress chapter_progress_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY chapter_progress_select ON public.chapter_progress FOR SELECT TO authenticated USING (((user_id = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text])))))));


--
-- Name: chapter_progress chapter_progress_update_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY chapter_progress_update_own ON public.chapter_progress FOR UPDATE TO authenticated USING ((user_id = ( SELECT auth.uid() AS uid))) WITH CHECK ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: chapters; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.chapters ENABLE ROW LEVEL SECURITY;

--
-- Name: chapters chapters_select_public; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY chapters_select_public ON public.chapters FOR SELECT TO authenticated USING (true);


--
-- Name: cohort_courses; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.cohort_courses ENABLE ROW LEVEL SECURITY;

--
-- Name: cohort_courses cohort_courses_select_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cohort_courses_select_all ON public.cohort_courses FOR SELECT USING (true);


--
-- Name: cohorts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.cohorts ENABLE ROW LEVEL SECURITY;

--
-- Name: cohorts cohorts_delete_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cohorts_delete_teacher ON public.cohorts FOR DELETE TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: cohorts cohorts_insert_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cohorts_insert_teacher ON public.cohorts FOR INSERT TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: cohorts cohorts_select_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cohorts_select_all ON public.cohorts FOR SELECT TO authenticated USING (true);


--
-- Name: cohorts cohorts_update_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY cohorts_update_teacher ON public.cohorts FOR UPDATE TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: content_versions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.content_versions ENABLE ROW LEVEL SECURITY;

--
-- Name: content_versions content_versions_anon_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY content_versions_anon_read ON public.content_versions FOR SELECT TO anon USING (((status = 'ok'::text) AND (superseded_by IS NULL)));


--
-- Name: content_versions content_versions_authenticated_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY content_versions_authenticated_read ON public.content_versions FOR SELECT TO authenticated USING (((status = 'ok'::text) AND (superseded_by IS NULL)));


--
-- Name: content_versions content_versions_service_role_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY content_versions_service_role_all ON public.content_versions TO service_role USING (true) WITH CHECK (true);


--
-- Name: course_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.course_events ENABLE ROW LEVEL SECURITY;

--
-- Name: course_events course_events_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY course_events_select ON public.course_events FOR SELECT TO authenticated USING (((created_by = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.enrollments e
  WHERE (((e.course_id)::text = (course_events.course_id)::text) AND (e.user_id = ( SELECT auth.uid() AS uid))))) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = 'admin'::text))))));


--
-- Name: course_prerequisites; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.course_prerequisites ENABLE ROW LEVEL SECURITY;

--
-- Name: course_reviews; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.course_reviews ENABLE ROW LEVEL SECURITY;

--
-- Name: courses; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.courses ENABLE ROW LEVEL SECURITY;

--
-- Name: courses courses_delete_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY courses_delete_teacher ON public.courses FOR DELETE TO authenticated USING (((created_by = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = 'admin'::text))))));


--
-- Name: courses courses_insert_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY courses_insert_teacher ON public.courses FOR INSERT TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: courses courses_select_published; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY courses_select_published ON public.courses FOR SELECT TO authenticated USING (((status = 'published'::text) OR (created_by = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = 'admin'::text))))));


--
-- Name: courses courses_update_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY courses_update_teacher ON public.courses FOR UPDATE TO authenticated USING (((created_by = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = 'admin'::text))))));


--
-- Name: daily_challenge_attempts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.daily_challenge_attempts ENABLE ROW LEVEL SECURITY;

--
-- Name: daily_challenge_options; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.daily_challenge_options ENABLE ROW LEVEL SECURITY;

--
-- Name: daily_challenge_pilot_reviews; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.daily_challenge_pilot_reviews ENABLE ROW LEVEL SECURITY;

--
-- Name: daily_challenge_question_events; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.daily_challenge_question_events ENABLE ROW LEVEL SECURITY;

--
-- Name: daily_challenge_questions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.daily_challenge_questions ENABLE ROW LEVEL SECURITY;

--
-- Name: daily_challenge_schedule; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.daily_challenge_schedule ENABLE ROW LEVEL SECURITY;

--
-- Name: daily_challenge_streaks; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.daily_challenge_streaks ENABLE ROW LEVEL SECURITY;

--
-- Name: daily_challenge_attempts dc_attempts_select_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY dc_attempts_select_own ON public.daily_challenge_attempts FOR SELECT TO authenticated USING ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: daily_challenge_options dc_options_select_via_question; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY dc_options_select_via_question ON public.daily_challenge_options FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.daily_challenge_questions q
  WHERE ((q.id = daily_challenge_options.question_id) AND (((q.status = 'published'::text) AND (q.rejected = false) AND (EXISTS ( SELECT 1
           FROM public.daily_challenge_schedule s
          WHERE ((s.question_id = q.id) AND (s.challenge_date <= ((now() AT TIME ZONE 'UTC'::text))::date))))) OR (EXISTS ( SELECT 1
           FROM public.profiles p
          WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))))))));


--
-- Name: daily_challenge_pilot_reviews dc_pilot_reviews_select_editorial; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY dc_pilot_reviews_select_editorial ON public.daily_challenge_pilot_reviews FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: daily_challenge_question_events dc_q_events_select_editorial; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY dc_q_events_select_editorial ON public.daily_challenge_question_events FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: daily_challenge_questions dc_questions_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY dc_questions_select ON public.daily_challenge_questions FOR SELECT TO authenticated USING (((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))) OR ((status = 'published'::text) AND (rejected = false) AND (EXISTS ( SELECT 1
   FROM public.daily_challenge_schedule s
  WHERE ((s.question_id = daily_challenge_questions.id) AND (s.challenge_date <= ((now() AT TIME ZONE 'UTC'::text))::date)))))));


--
-- Name: daily_challenge_schedule dc_schedule_select_visible; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY dc_schedule_select_visible ON public.daily_challenge_schedule FOR SELECT TO authenticated USING (((challenge_date <= ((now() AT TIME ZONE 'UTC'::text))::date) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text])))))));


--
-- Name: daily_challenge_streaks dc_streaks_select_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY dc_streaks_select_own ON public.daily_challenge_streaks FOR SELECT TO authenticated USING ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: enrollments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.enrollments ENABLE ROW LEVEL SECURITY;

--
-- Name: enrollments enrollments_delete_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY enrollments_delete_own ON public.enrollments FOR DELETE TO authenticated USING ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: enrollments enrollments_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY enrollments_select ON public.enrollments FOR SELECT TO authenticated USING (((user_id = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text])))))));


--
-- Name: modules; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.modules ENABLE ROW LEVEL SECURITY;

--
-- Name: modules modules_select_public; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY modules_select_public ON public.modules FOR SELECT TO authenticated USING (true);


--
-- Name: notifications; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

--
-- Name: notifications notifications_select_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY notifications_select_own ON public.notifications FOR SELECT TO authenticated USING ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: notifications notifications_update_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY notifications_update_own ON public.notifications FOR UPDATE TO authenticated USING ((user_id = ( SELECT auth.uid() AS uid))) WITH CHECK ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: course_prerequisites prereqs_delete_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY prereqs_delete_teacher ON public.course_prerequisites FOR DELETE TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: course_prerequisites prereqs_insert_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY prereqs_insert_teacher ON public.course_prerequisites FOR INSERT TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: course_prerequisites prereqs_select_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY prereqs_select_all ON public.course_prerequisites FOR SELECT TO authenticated USING ((( SELECT auth.uid() AS uid) IS NOT NULL));


--
-- Name: profiles; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

--
-- Name: profiles profiles_select_self; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY profiles_select_self ON public.profiles FOR SELECT TO authenticated USING ((id = ( SELECT auth.uid() AS uid)));


--
-- Name: profiles profiles_service_role_full; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY profiles_service_role_full ON public.profiles TO service_role USING (true) WITH CHECK (true);


--
-- Name: profiles profiles_update_own_safe_fields; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY profiles_update_own_safe_fields ON public.profiles FOR UPDATE TO authenticated USING ((( SELECT auth.uid() AS uid) = id)) WITH CHECK ((( SELECT auth.uid() AS uid) = id));


--
-- Name: quiz_answers; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.quiz_answers ENABLE ROW LEVEL SECURITY;

--
-- Name: quiz_answers quiz_answers_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quiz_answers_insert_own ON public.quiz_answers FOR INSERT TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM public.quiz_attempts qa
  WHERE ((qa.id = quiz_answers.attempt_id) AND (qa.user_id = ( SELECT auth.uid() AS uid))))));


--
-- Name: quiz_answers quiz_answers_select_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quiz_answers_select_own ON public.quiz_answers FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.quiz_attempts qa
  WHERE ((qa.id = quiz_answers.attempt_id) AND ((qa.user_id = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
           FROM public.profiles p
          WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))))))));


--
-- Name: quiz_attempts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.quiz_attempts ENABLE ROW LEVEL SECURITY;

--
-- Name: quiz_attempts quiz_attempts_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quiz_attempts_insert_own ON public.quiz_attempts FOR INSERT TO authenticated WITH CHECK ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: quiz_attempts quiz_attempts_select_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quiz_attempts_select_own ON public.quiz_attempts FOR SELECT TO authenticated USING (((user_id = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text])))))));


--
-- Name: quiz_extra_attempts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.quiz_extra_attempts ENABLE ROW LEVEL SECURITY;

--
-- Name: quiz_extra_attempts quiz_extra_attempts_select_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quiz_extra_attempts_select_own ON public.quiz_extra_attempts FOR SELECT TO authenticated USING (((user_id = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text])))))));


--
-- Name: quiz_options; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.quiz_options ENABLE ROW LEVEL SECURITY;

--
-- Name: quiz_options quiz_options_select_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quiz_options_select_all ON public.quiz_options FOR SELECT TO authenticated USING ((( SELECT auth.uid() AS uid) IS NOT NULL));


--
-- Name: quiz_questions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.quiz_questions ENABLE ROW LEVEL SECURITY;

--
-- Name: quiz_questions quiz_questions_select_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quiz_questions_select_all ON public.quiz_questions FOR SELECT TO authenticated USING ((( SELECT auth.uid() AS uid) IS NOT NULL));


--
-- Name: quizzes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.quizzes ENABLE ROW LEVEL SECURITY;

--
-- Name: quizzes quizzes_delete_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quizzes_delete_teacher ON public.quizzes FOR DELETE TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: quizzes quizzes_insert_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quizzes_insert_teacher ON public.quizzes FOR INSERT TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: quizzes quizzes_select_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quizzes_select_all ON public.quizzes FOR SELECT TO authenticated USING ((( SELECT auth.uid() AS uid) IS NOT NULL));


--
-- Name: quizzes quizzes_update_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY quizzes_update_teacher ON public.quizzes FOR UPDATE TO authenticated USING ((EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text]))))));


--
-- Name: course_reviews reviews_delete_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY reviews_delete_own ON public.course_reviews FOR DELETE TO authenticated USING ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: course_reviews reviews_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY reviews_insert_own ON public.course_reviews FOR INSERT TO authenticated WITH CHECK ((user_id = ( SELECT auth.uid() AS uid)));


--
-- Name: course_reviews reviews_select_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY reviews_select_all ON public.course_reviews FOR SELECT TO authenticated USING ((( SELECT auth.uid() AS uid) IS NOT NULL));


--
-- Name: student_grades; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.student_grades ENABLE ROW LEVEL SECURITY;

--
-- Name: student_grades student_grades_select; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY student_grades_select ON public.student_grades FOR SELECT TO authenticated USING (((student_id = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text])))))));


--
-- Name: assignment_submissions submissions_insert_own; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY submissions_insert_own ON public.assignment_submissions FOR INSERT TO authenticated WITH CHECK ((student_id = ( SELECT auth.uid() AS uid)));


--
-- Name: assignment_submissions submissions_select_own_or_teacher; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY submissions_select_own_or_teacher ON public.assignment_submissions FOR SELECT TO authenticated USING (((student_id = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM public.profiles p
  WHERE ((p.id = ( SELECT auth.uid() AS uid)) AND (p.role = ANY (ARRAY['teacher'::text, 'admin'::text])))))));


--
-- Name: translation_jobs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.translation_jobs ENABLE ROW LEVEL SECURITY;

--
-- Name: translation_jobs translation_jobs_no_client_access; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY translation_jobs_no_client_access ON public.translation_jobs TO anon, authenticated USING (false) WITH CHECK (false);


--
-- PostgreSQL database dump complete
--

\unrestrict 2XKTDS5XRmU2AGeGBdr3ouCL2xQnTL8Lw6qQrf0bhJatveYzrTmxtUS4acfUht6

