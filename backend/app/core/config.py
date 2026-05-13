import logging
import os

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

    SUPABASE_URL: str
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
    CORS_ORIGIN_REGEX: str = (
        r"^https://equip-frontend(?:-[\w-]+)?\.vercel\.app$"
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
    # gemini-2.5-flash-lite: no "thinking" tokens (translation doesn't need
    # them) so the full GEMINI_MAX_OUTPUT_TOKENS budget goes to the actual
    # translation. The previous default ``gemini-flash-latest`` resolves to
    # the thinking-enabled 2.5-Flash, which consumed the budget on long
    # course blocks and tripped finishReason=MAX_TOKENS. Lite is also
    # cheaper for our volume. Switch to ``gemini-2.5-flash`` only if a
    # specific course needs the higher quality and you've raised the
    # output cap accordingly (or set thinkingConfig in the payload).
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash-lite", description="Gemini model id used for translations")
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

    @model_validator(mode="after")
    def load_alternative_env_vars(self):
        """Support alternative env var names from Vercel/Supabase integration."""
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

        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL or POSTGRES_URL must be set")
        if not self.JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY or SUPABASE_JWT_SECRET must be set")

        return self

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.CORS_ORIGINS:
            return ["http://localhost:3000", "http://localhost:5173"]
        origins = [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return [o for o in origins if o]


settings = Settings()
