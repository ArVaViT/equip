import logging
from collections.abc import Generator
from urllib.parse import urlparse

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import env_flag, settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None

IS_SERVERLESS = env_flag("VERCEL", "AWS_LAMBDA_FUNCTION_NAME")


def _get_engine() -> Engine:
    """Lazy initialization of the database engine."""
    global _engine, _SessionLocal

    if _engine is not None:
        return _engine

    try:
        db_url = settings.DATABASE_URL
    except Exception as e:
        logger.error(f"Failed to load DATABASE_URL: {e}")
        raise RuntimeError(f"DATABASE_URL not configured: {e}") from e

    if not db_url:
        raise RuntimeError("DATABASE_URL is empty or not set")

    if db_url and "sslmode" not in db_url:
        separator = "&" if "?" in db_url else "?"
        db_url = f"{db_url}{separator}sslmode=require"

    # Serverless DB-shape guard. The per-instance pool (below) keeps 1-3
    # connections per warm instance, so on Vercel/Lambda prod MUST point at
    # Supabase's transaction pooler (:6543), not the direct Postgres endpoint
    # (:5432). Direct connections cap at ~15-60 backends and exhaust almost
    # immediately under a launch spike. Nothing else enforces this documented
    # invariant (.env.example / DEPLOYMENT.md), so warn loudly at boot rather
    # than discover it during an incident.
    if IS_SERVERLESS:
        try:
            _port = urlparse(db_url).port
        except ValueError:
            _port = None
        if _port == 5432:
            logger.warning(
                "DATABASE_URL targets port 5432 (DIRECT Postgres) under serverless. "
                "With NullPool this opens one backend per warm instance and will "
                "exhaust connections under load — use the Supabase TRANSACTION "
                "POOLER (:6543) instead."
            )

    try:
        try:
            import psycopg2 as _psycopg2

            _ = _psycopg2  # verify driver is importable
        except ImportError as e:
            raise RuntimeError(
                "PostgreSQL driver (psycopg2-binary) is not installed. "
                "Please ensure psycopg2-binary is in requirements.txt."
            ) from e

        pool_kwargs: dict = {
            "connect_args": {
                # 5s (was 10) so a saturated pooler sheds load fast under a
                # spike instead of queueing each request for 10s. A healthy
                # pooler connect is sub-second; this only bites when saturated.
                # NOTE: do NOT put statement_timeout in an ``options`` startup
                # parameter here — Supavisor transaction pooling silently drops
                # it (verified on prod 2026-06-11: SHOW statement_timeout
                # returned the 2min cluster default). The real bound is the
                # SET LOCAL emitted per-transaction below.
                "connect_timeout": 5,
            },
            "pool_pre_ping": True,
            "echo": False,
        }

        if IS_SERVERLESS:
            # Vercel keeps the Python process warm across invocations (the
            # module-cached engine, JWT cache and Gemini client all rely on
            # it), so a per-instance pool amortises the TCP+TLS+auth handshake
            # to the pooler (~10-30ms) instead of paying it on EVERY request
            # as NullPool did. `pool_recycle` guards against the pooler
            # silently dropping idle clients.
            #
            # This was 1+2, and that number was chosen when requests arrived
            # one at a time. They do not: opening a single chapter fires
            # **seven** concurrent calls — course, progress, blocks,
            # announcements, notifications, legal, cohorts — so four of them
            # queued behind three connections, and `pool_timeout` expiring
            # showed up in production as
            # `QueuePool limit of size 1 overflow 2 reached, connection timed
            # out` (2026-08-12). Removing a request waterfall on the chapter
            # page made it worse rather than better: the calls stopped
            # serialising on each other and started serialising here.
            #
            # 5+5 is measured, not guessed. Postgres `max_connections` is 60
            # with 16 in use; in front of it is a **transaction** pooler,
            # which multiplexes many client sessions onto few backend
            # connections, so ten client slots per warm instance cost the
            # database almost nothing. It is enough for one page's seven
            # parallel calls with headroom, and far under any limit either
            # side of the pooler.
            pool_kwargs.update(
                {
                    "pool_size": 5,
                    "max_overflow": 5,
                    "pool_recycle": 300,
                    "pool_timeout": 10,
                }
            )
        else:
            pool_kwargs.update(
                {
                    "pool_size": 5,
                    "max_overflow": 10,
                    "pool_recycle": 300,
                    "pool_timeout": 20,
                }
            )

        _engine = create_engine(db_url, **pool_kwargs)

        if _engine.dialect.name == "postgresql":
            # Transaction-scoped statement timeout. SET LOCAL is the only
            # form that survives Supavisor transaction pooling (a session
            # SET would leak onto whatever client gets the server connection
            # next; the ``options`` startup parameter is dropped entirely).
            # One cheap round-trip per transaction restores the designed 30s
            # bound — without it a pathological query holds a pooler slot
            # for the 2min cluster default.
            @event.listens_for(_engine, "begin")
            def _set_statement_timeout(conn: Connection) -> None:
                conn.exec_driver_sql("SET LOCAL statement_timeout = '30s'")

        logger.info("Database engine created successfully")

        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    except RuntimeError:
        raise
    except Exception as e:
        error_msg = f"Failed to create database engine: {e!s}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e

    return _engine


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session.

    pool_pre_ping on the engine already validates connections,
    so we skip a manual SELECT 1 here.
    """
    from fastapi import HTTPException, status

    try:
        _get_engine()
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection error",
        ) from None

    if _SessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database session factory not initialized",
        )

    db = _SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error("Database error: %s", e)
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
