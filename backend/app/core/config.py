import logging
import os

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Models whose cost, speed and translation quality have actually been
# measured against production strings — see the ``GEMINI_MODEL`` field
# for the numbers and the date. Anything else boots with a warning:
# running an unmeasured model is allowed, running one by accident is
# what happened for 81 days.
MEASURED_GEMINI_MODELS = frozenset({"gemini-2.5-flash-lite"})


def call_reserve_seconds(gemini_timeout_seconds: float, gemini_max_retries: int = 2) -> float:
    """The worst case for one Gemini call, in seconds.

    A call can take its read timeout on each of ``max_retries + 1``
    attempts, plus the backoff between them, and a couple of seconds go
    to the commit and the promotion check that follow the last one.
    ``services/translation/budget.py`` keeps exactly this much back
    before authorising a call, so the invocation is never killed with a
    request in flight.

    It lives here, rather than next to the budget it serves, because the
    validator below has to refuse a deployment whose worker budget is
    smaller than this — and importing the budget module from config
    closes a cycle through ``app.services.translation.__init__``. One
    copy of the arithmetic, in the layer that both sides can see.
    """
    attempts = gemini_max_retries + 1
    backoff = float(sum(2**n for n in range(gemini_max_retries)))
    return gemini_timeout_seconds * attempts + backoff + 2.0


def env_flag(*names: str) -> bool:
    """True when any of the named environment variables is set non-empty.

    Shared helper for the boot-time platform flags (production /
    serverless / trusted-proxy) that were previously computed with a
    copy-pasted ``bool(os.environ.get(...) or os.environ.get(...))`` at
    each site. Reads the environment at call time — call sites evaluate
    it once at module import, exactly like the inline expressions did.
    """
    return any(os.environ.get(name) for name in names)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    # All boot-critical fields are ``Optional`` so the app process can boot
    # even on a Vercel preview/development deployment that wasn't given the
    # full env-var set. A missing value here doesn't crash on import — it
    # bubbles up at request time through the existing 503 handlers in
    # ``app.core.database.get_db`` / ``app.core.security.decode_access_token``.
    # The list of missing critical fields is exposed via ``runtime_ready_errors()``
    # so ``app.main`` can log a single startup warning instead of letting a
    # Pydantic ``ValidationError`` traceback land on every favicon scrape.
    SUPABASE_URL: str | None = Field(default=None, description="Supabase project URL")
    # Server-side Supabase key (admin queries only — e.g. reading auth.users
    # to sync ``profiles`` rows). Also read from the legacy SUPABASE_KEY env
    # var for backwards compatibility with early deployments — see
    # load_alternative_env_vars() below.
    SUPABASE_SERVICE_ROLE_KEY: str | None = Field(default=None, description="Supabase service-role key (server-only)")

    DATABASE_URL: str | None = Field(default=None, description="Database connection URL")

    JWT_SECRET_KEY: str | None = Field(default=None, description="JWT secret key")
    JWT_ALGORITHM: str = "HS256"

    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:5173,"
        "https://equipbible.com,https://www.equipbible.com,"
        "https://equip-frontend.vercel.app"
    )
    # Anchored to the Vercel team slug ``vadyms-projects-dfb6f76f``. The
    # previous pattern (``equip-frontend(?:-[\w-]+)?\.vercel\.app``) would
    # match any ``equip-frontend-X.vercel.app`` URL, including projects
    # owned by other Vercel accounts -- an attacker could create
    # ``equip-frontend-evil.vercel.app`` under their own team and trick
    # the browser into a same-origin context against our backend with
    # ``allow_credentials=True``. Locking the suffix to our team slug
    # closes that hole. The bare ``equip-frontend.vercel.app`` alias is
    # also allowed because Vercel keeps the canonical project URL as a
    # team-agnostic redirect.
    CORS_ORIGIN_REGEX: str = (
        r"^https://equip-frontend(?:-[\w-]+)?-vadyms-projects-dfb6f76f\.vercel\.app$"
        r"|^https://equip-frontend\.vercel\.app$"
        r"|^https://(?:www\.)?equipbible\.com$"
        r"|^http://localhost:\d+$"
    )

    # Server-only translation-pipeline secrets. Never alias under ``VITE_*`` —
    # the API key would leak into the public bundle. The pipeline is opt-in:
    # when the key is absent the translation service degrades to a no-op so
    # dev environments without billing can still run the rest of the app.
    # ``SecretStr`` keeps the value out of any incidental ``Settings``
    # repr/log dump; callers must use ``.get_secret_value()`` to read it.
    GEMINI_API_KEY: SecretStr | None = Field(default=None, description="Google AI Studio API key (server-only)")
    # YouVersion Platform key for the Verse of the Day card. Optional the
    # same way GEMINI_API_KEY is: when unset (CI, local dev without setup)
    # the verse service raises ``VerseOfTheDayUnavailable`` and the route
    # returns 404 so the frontend quietly hides the card.
    YOUVERSION_API_KEY: SecretStr | None = Field(default=None, description="YouVersion Platform API key (server-only)")
    # Direct backend→Resend calls for transactional mail that isn't a
    # Supabase Auth lifecycle event (signup/recovery/magic_link don't go
    # through here -- those stay on supabase/functions/send-email, which is
    # a Supabase Auth email hook and can't be reused for arbitrary sends).
    # Invitation emails are the first user of this. Optional the same way
    # the other provider keys are: unset means the invite is created but
    # send_invitation_email logs and no-ops instead of raising, so a missing
    # key degrades to "admin must share the link manually" rather than a
    # 500 on invite creation.
    RESEND_API_KEY: SecretStr | None = Field(default=None, description="Resend API key (server-only)")
    # Base URL for links embedded in backend-sent emails (invite accept
    # link, etc). No existing Settings field carried this -- other call
    # sites hardcode "https://equipbible.com" inline (see app/main.py,
    # calendar_ical.py). Kept as a real setting (not another hardcode) so
    # a preview/staging deployment can point invite links at itself.
    FRONTEND_URL: str = Field(default="https://equipbible.com", description="Public frontend origin for email links")
    # ``gemini-2.5-flash-lite``, measured rather than assumed. Numbers
    # from 2026-08-17, twelve real production strings translated into
    # German and judged by our own ``validation.py``:
    #
    #   model                  passed   per string   thinking tokens
    #   gemini-2.5-flash-lite   12/12       0.5 s              0
    #   gemini-flash-latest     12/12       3.1 s         10,046 (total)
    #
    # Same verdicts from the validator, six times faster, and ~840
    # "thinking" tokens per string that nobody reads and everyone pays
    # for — they bill as output.
    #
    # Two things that were believed here and are not true:
    #
    # * "Lite has no thinking tokens." Every model the API lists today,
    #   lite included, reports ``thinking: true``. Lite happens to spend
    #   none on this work, which is the property we want, but it is a
    #   measurement and not a guarantee — re-measure when changing model.
    # * "Set thinkingConfig to switch it off." On ``gemini-flash-latest``,
    #   ``thinkingBudget: 0`` moved the count from 1227 to 1066. It does
    #   not turn thinking off; only choosing a different model does.
    #
    # Pin a version rather than riding ``-latest``: the alias moves under
    # you, and the families disagree about the payload — Gemini 3.x
    # rejects ``thinkingConfig.thinkingBudget`` with a 400.
    #
    # This default was already correct in the code and wrong in
    # production for 81 days, because the Vercel env var overrode it.
    # A default nobody deploys is a comment.
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash-lite", description="Gemini model id used for translations")
    #: The model that reads a finished translation and objects to it.
    #:
    #: Deliberately not the same one that wrote it — asking a model to
    #: grade its own answer gets agreement, and the defects that survive
    #: are exactly the ones it cannot see in itself.
    #:
    #: Deliberately a different generation, too, and this was measured
    #: rather than assumed. On the defects an editor actually found in
    #: production — the Ethiopian eunuch turned into a Pentecostal, "the
    #: first half" of the Bible rendered as an accounting half-year, the
    #: invented word "Unabgewaschen" — the translation model catches four
    #: of six and this one catches five, with no false objections on
    #: correct text in either case. A reviewer that flags good work is
    #: worse than none: every row it touches becomes a person's problem.
    GEMINI_REVIEW_MODEL: str = Field(
        default="gemini-3.5-flash-lite",
        description="Gemini model id used to review finished translations",
    )
    # 30s headroom: a 5 KB Russian HTML block (lesson-overview callout in
    # the Acts course backfill) on ``gemini-flash-latest`` regularly takes
    # 18-25s to translate to English. The earlier 15s default produced
    # ``status='failed'`` rows for 7/40 chapter blocks. Combined with the
    # bounded retry schedule in ``GeminiTranslationProvider`` (≤0.3s budget)
    # this still keeps a single bad batch from monopolising a worker.
    GEMINI_TIMEOUT_SECONDS: float = Field(default=30.0, description="Per-request timeout for Gemini calls")
    # 8192 is the per-call ceiling on ``gemini-flash-latest``; the previous
    # 4096 default truncated long course-block translations (e.g. an 11.8 KB
    # Russian HTML appendix in the Acts course came back at 715 chars with
    # ``finishReason='MAX_TOKENS'``). Bumping to the model's actual ceiling
    # plus the new ``finishReason`` check in ``GeminiTranslationProvider``
    # closes that hole. Cost-wise the cap only matters when actually emitted.
    GEMINI_MAX_OUTPUT_TOKENS: int = Field(default=8192, description="Cap on generation length")
    # Anti-abuse cap on live (non-deleted) courses per teacher. Generous on
    # purpose — a real Bible-school teacher authors a handful of courses; a
    # runaway script or a misunderstanding authors hundreds. Admins exempt.
    MAX_COURSES_PER_TEACHER: int = Field(
        default=50,
        description="Max live courses a single teacher can own (admins exempt)",
    )
    # Minimum spacing between two Gemini calls from the same worker, in
    # seconds. ``0`` (default) is the right value for production: course
    # publishing is naturally bursty-but-sparse and rarely trips Gemini's
    # 15 RPM free-tier limit. Backfill scripts that fire hundreds of
    # requests back-to-back should set this to ``4.5`` (≈13 RPM, one slot
    # of headroom under the 15 RPM cap) to avoid 429-rate-limit storms.
    GEMINI_MIN_INTERVAL_SECONDS: float = Field(
        default=0.0,
        description="Min seconds between two Gemini calls from the same worker (RPM throttle)",
    )
    # Shared-secret auth for the translation worker endpoint
    # (``POST /api/v1/internal/translation-worker``). The cron driver
    # — Vercel Cron, Supabase Edge Function, or anything else hitting
    # the route — signs its request with this value in the
    # ``X-Worker-Secret`` header. When the secret is unset the
    # endpoint refuses every request, which is what you want in dev
    # environments that don't run the queue yet.
    TRANSLATION_WORKER_SECRET: SecretStr | None = Field(
        default=None,
        description="Shared secret the cron driver presents to drain the translation queue",
    )
    # Feature flag that swaps the publish path from sync orchestrator
    # calls (one Gemini call per cv field, up to 100+ for a chapter-
    # heavy course, all inside the teacher's request) to a queue
    # enqueue (one DB insert). The cron driver from Phase 5aw drains
    # the queue out-of-band. Off by default so a deploy without the
    # cron configured stays on the legacy sync path; flip ON after
    # confirming the worker is running.
    TRANSLATION_QUEUE_ENABLED: bool = Field(
        default=False,
        description="Use the queue-based publish path instead of sync orchestrator calls",
    )
    # How long one worker tick may spend translating before it hands the
    # job back unfinished. Must leave room, inside the function's
    # ``maxDuration`` (300 s in backend/vercel.json), for the one
    # provider call the budget may still authorise — worst case
    # ``GEMINI_TIMEOUT_SECONDS`` on each of three attempts plus backoff,
    # which ``worker_budget`` reserves automatically. 180 + ~96 leaves
    # roughly twenty seconds of headroom for the commit and the
    # promotion check.
    #
    # This is the setting that makes a large course finish. Without a
    # budget the tick simply ran until the platform killed it, which
    # left the job in ``processing`` with nothing recorded — 161 such
    # attempts on one course in August 2026.
    #
    # It is also half of a pair: set it below the reserve and the worker
    # can never start a call at all. See
    # ``refuse_a_worker_budget_that_cannot_afford_one_call`` below, which
    # will not let the process boot in that state.
    TRANSLATION_WORKER_BUDGET_SECONDS: float = Field(
        default=180.0,
        description="Wall-clock allowance for one translation worker tick",
    )

    @model_validator(mode="after")
    def load_alternative_env_vars(self):
        """Support alternative env var names from Vercel/Supabase integration."""
        # An empty ``GEMINI_MODEL`` env var (e.g. an operator set the Vercel
        # variable to ``""``) would otherwise become the literal string ""
        # in the request URL — ``models/:generateContent`` — and Gemini
        # returns 404. Treat blank as "use the default" instead.
        if not self.GEMINI_MODEL or not self.GEMINI_MODEL.strip():
            self.GEMINI_MODEL = Settings.model_fields["GEMINI_MODEL"].default

        # Say so when the deployment is not running the model we measured.
        #
        # Not a refusal — an operator swapping models deliberately is a
        # legitimate thing to do, and a deploy that will not boot over a
        # model name is worse than one that translates differently. But
        # it must not be silent: production spent 81 days on
        # ``gemini-flash-latest`` while this file said flash-lite, at
        # roughly 840 wasted "thinking" tokens per string and six times
        # the latency, and nothing anywhere said a word. WARNING ships to
        # Datadog, so the next divergence is one search away.
        if self.GEMINI_MODEL not in MEASURED_GEMINI_MODELS:
            logger.warning(
                "GEMINI_MODEL is %r, which is not one of the measured models (%s). "
                "Cost, latency and translation quality are unverified for it.",
                self.GEMINI_MODEL,
                ", ".join(sorted(MEASURED_GEMINI_MODELS)),
            )

        if not self.SUPABASE_SERVICE_ROLE_KEY:
            # Accept the legacy SUPABASE_KEY name from older deployments.
            # Anon keys are NEVER accepted as a server-side secret.
            legacy = os.getenv("SUPABASE_KEY")
            if legacy:
                logger.warning("SUPABASE_KEY is deprecated; set SUPABASE_SERVICE_ROLE_KEY explicitly")
                self.SUPABASE_SERVICE_ROLE_KEY = legacy

        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("POSTGRES_PRISMA_URL")
            )
        if self.DATABASE_URL:
            self.DATABASE_URL = self.DATABASE_URL.strip()

        supabase_jwt = os.getenv("SUPABASE_JWT_SECRET")
        if supabase_jwt:
            self.JWT_SECRET_KEY = supabase_jwt.strip()
        elif not self.JWT_SECRET_KEY:
            self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
        if self.JWT_SECRET_KEY:
            self.JWT_SECRET_KEY = self.JWT_SECRET_KEY.strip()

        # Critical-field validation moved to ``runtime_ready_errors()`` so
        # boot succeeds on partially-configured environments (preview deploys
        # without prod env vars) instead of crashing on module import and
        # converting every favicon GET into a 500 with a full Pydantic stack
        # trace. Real production must still surface missing config — the
        # startup warning in ``app.main`` plus per-request 503s via the DB
        # / auth dependencies cover that without spamming the error stream.

        return self

    @model_validator(mode="after")
    def refuse_a_worker_budget_that_cannot_afford_one_call(self):
        """Refuse to boot when the tick can never authorise a single call.

        ``worker_budget`` keeps back the worst case for one provider
        call — ``GEMINI_TIMEOUT_SECONDS`` on each of three attempts plus
        backoff plus two seconds. When that reserve is as large as
        ``TRANSLATION_WORKER_BUDGET_SECONDS``, ``can_afford_one_call()``
        is already False at t=0: the pass sets ``incomplete`` before
        making a single call, ``made_progress`` is False, and the job
        goes back to ``queued`` while the worker answers ``"paused"``.
        Paused reads as healthy. Nothing translates, nothing errors, and
        the same job is re-claimed every minute for as long as the
        deployment stands.

        The values are one raise apart. ``GEMINI_TIMEOUT_SECONDS`` has
        already been raised once in this file (15 → 30, for a 5 KB
        Russian block); at the 180 s default budget the next such raise
        crosses at 58.33 s. This is why the check exists at boot, where
        an operator sees it, rather than as a silence in production.
        """
        reserve = call_reserve_seconds(self.GEMINI_TIMEOUT_SECONDS)
        if reserve >= self.TRANSLATION_WORKER_BUDGET_SECONDS:
            raise ValueError(
                f"TRANSLATION_WORKER_BUDGET_SECONDS={self.TRANSLATION_WORKER_BUDGET_SECONDS} is too small for "
                f"GEMINI_TIMEOUT_SECONDS={self.GEMINI_TIMEOUT_SECONDS}: one provider call reserves "
                f"{reserve} s (timeout on each of 3 attempts + 3 s backoff + 2 s), so the worker could never "
                f"start a call. Raise TRANSLATION_WORKER_BUDGET_SECONDS above {reserve} (staying under the "
                f"function's maxDuration) or lower GEMINI_TIMEOUT_SECONDS below "
                f"{(self.TRANSLATION_WORKER_BUDGET_SECONDS - 5.0) / 3.0:.2f}."
            )
        return self

    def runtime_ready_errors(self) -> list[str]:
        """Names of critical fields not configured.

        Returns ``[]`` when the app can serve authenticated API traffic;
        otherwise lists the missing env-var names so ``app.main`` can emit
        a single, scannable startup warning. Static surfaces (``/health``,
        ``/favicon.*``, ``/``) work regardless of the result.
        """
        missing: list[str] = []
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        if not self.JWT_SECRET_KEY:
            missing.append("JWT_SECRET_KEY")
        if not self.SUPABASE_URL:
            missing.append("SUPABASE_URL")
        return missing

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.CORS_ORIGINS:
            return ["http://localhost:3000", "http://localhost:5173"]
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return [o for o in origins if o]


settings = Settings()
