import logging
import os
from collections.abc import Generator
from urllib.parse import urlparse

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None

IS_SERVERLESS = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


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

    # Serverless DB-shape guard. NullPool (below) opens ONE connection per warm
    # instance, so on Vercel/Lambda prod MUST point at Supabase's transaction
    # pooler (:6543), not the direct Postgres endpoint (:5432). A direct
    # connection caps at ~15-60 backends and exhausts almost immediately under a
    # launch spike. Nothing else enforces this documented invariant
    # (.env.example / DEPLOYMENT.md), so warn loudly at boot rather than discover
    # it during an incident.
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
                "connect_timeout": 5,
                "options": "-c statement_timeout=30000",
            },
            "pool_pre_ping": True,
            "echo": False,
        }

        if IS_SERVERLESS:
            pool_kwargs["poolclass"] = NullPool
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
