-- A translation is only as good as the rules that produced it.
--
-- Today a machine row is skipped whenever its source hash still matches:
-- same source text, same translation, nothing to do. That is right for the
-- question it was built to answer — "has the author changed this?" — and it
-- silently answers a second question wrongly: "are our translations still the
-- best we know how to make?"
--
-- They were not. The glossary that settles `церковь` → `Gemeinde`, the rules
-- naming each language's calques, the correcting pass that replaces a rejected
-- wording, the verse substitution that stopped handing Scripture to a machine
-- translator — every one of those improved what a new translation looks like,
-- and none of them touched the several thousand rows already stored. The
-- catalogue kept the quality of the day it was translated.
--
-- Fixing that by hand is a person with a list, which is the thing this project
-- keeps deciding not to build. So the rows carry the version of the pipeline
-- that made them, and a row made by an older pipeline is treated exactly like
-- a row that is missing: the sweep finds it, the queue picks it up, and the
-- catalogue re-translates itself in the background at three courses a tick.
--
-- What this buys, and it is the point: improving translation quality becomes
-- editing a prompt and raising a constant. It costs no migration, no script,
-- and no evening.
--
-- 0 means "made before anyone was counting". Every existing row gets it, and
-- every existing row is therefore due for another pass — which is correct:
-- they were all made before today's rules existed.

ALTER TABLE public.content_versions
    ADD COLUMN translator_version SMALLINT NOT NULL DEFAULT 0;

ALTER TABLE public.staged_content_versions
    ADD COLUMN translator_version SMALLINT NOT NULL DEFAULT 0;

-- The sweep's question is "any machine rows left behind by an old pipeline?",
-- asked over and over across the whole table. Partial, because human rows are
-- never re-translated and settled rows are the overwhelming majority.
CREATE INDEX ix_content_versions_stale_translator
    ON public.content_versions (translator_version)
    WHERE superseded_by IS NULL AND origin = 'mt';

COMMENT ON COLUMN public.content_versions.translator_version IS
    'Which generation of the translation pipeline produced this row. Lower than the current TRANSLATOR_VERSION means the row predates the rules now in force and is due for another pass. 0 = made before this was tracked. Human rows keep 0 and are never re-translated.';
