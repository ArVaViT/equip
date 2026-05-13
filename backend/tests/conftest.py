"""Shared test fixtures for the Equip API backend.

Sets up an in-memory SQLite database so tests run without any external
services.  PgUUID / postgresql.JSON columns compile to generic types
automatically via SQLAlchemy 2.x dialect fallback.
"""

import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/testdb")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole

# ---------------------------------------------------------------------------
# In-memory SQLite engine shared across the entire test session
# ---------------------------------------------------------------------------

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def _enable_fk(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


TestSessionFactory = sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

# Stable UUIDs so tests can reference them predictably
TEACHER_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
STUDENT_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ADMIN_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

# ---------------------------------------------------------------------------
# Per-test table lifecycle — drop/create keeps every test fully isolated
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_tables():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def _clear_rate_limit():
    """Reset in-memory rate-limiter between tests to prevent 429s."""
    from app.middleware.rate_limit import RateLimitMiddleware

    def _reset(application):
        stack = getattr(application, "middleware_stack", None)
        while stack is not None:
            if isinstance(stack, RateLimitMiddleware):
                stack._hits.clear()
                return
            stack = getattr(stack, "app", None)

    _reset(app)
    yield
    _reset(app)


# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------


@pytest.fixture()
def db() -> Session:
    session = TestSessionFactory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _make_teacher() -> User:
    return User(
        id=TEACHER_ID,
        email="teacher@example.com",
        full_name="Test Teacher",
        role=UserRole.TEACHER.value,
    )


def _make_student() -> User:
    return User(
        id=STUDENT_ID,
        email="student@example.com",
        full_name="Test Student",
        role=UserRole.STUDENT.value,
    )


def _make_admin() -> User:
    return User(
        id=ADMIN_ID,
        email="admin@example.com",
        full_name="Test Admin",
        role=UserRole.ADMIN.value,
    )


@pytest.fixture()
def teacher(db: Session) -> User:
    user = _make_teacher()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def student(db: Session) -> User:
    user = _make_student()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def admin(db: Session) -> User:
    user = _make_admin()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# FastAPI TestClient — authenticated as teacher by default
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(db: Session, teacher: User) -> TestClient:
    """TestClient where every request is authenticated as the seeded teacher."""

    def _override_db():
        yield db

    def _override_user():
        return teacher

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_optional_user] = _override_user

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc

    app.dependency_overrides.clear()


@pytest.fixture()
def student_client(db: Session, teacher: User, student: User) -> TestClient:
    """TestClient authenticated as the seeded student (teacher also seeded)."""

    def _override_db():
        yield db

    def _override_user():
        return student

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_optional_user] = _override_user

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc

    app.dependency_overrides.clear()


@pytest.fixture()
def admin_client(db: Session, teacher: User, admin: User) -> TestClient:
    """TestClient authenticated as a seeded admin (teacher also seeded
    for course-authorship scenarios where admin manages teacher's courses)."""

    def _override_db():
        yield db

    def _override_user():
        return admin

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_optional_user] = _override_user

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc

    app.dependency_overrides.clear()


@pytest.fixture()
def anon_client(db: Session, teacher: User) -> TestClient:
    """TestClient with ``get_optional_user`` forced to None.

    Note: it overwrites the same ``app.dependency_overrides`` slot as
    :func:`client`. If a test needs both, list ``anon_client`` *after* ``client``
    when the anonymous behaviour must win for the final request.
    """

    def _override_db():
        yield db

    def _override_anon():
        return None

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_optional_user] = _override_anon

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc

    app.dependency_overrides.clear()
