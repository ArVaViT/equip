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
from app.legal import LEGAL_DOCUMENTS
from app.main import app
from app.models.course import Chapter, Module
from app.models.legal_acceptance import LegalAcceptance
from app.models.organization import Organization
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


#: The organization every test row belongs to unless it says otherwise.
#: Production has UCOAT; the tests have this, seeded per test alongside
#: the tables.
TEST_ORGANIZATION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.fixture(autouse=True)
def _reset_tables():
    Base.metadata.create_all(bind=test_engine)
    with test_engine.begin() as conn:
        conn.execute(
            Organization.__table__.insert().values(
                id=TEST_ORGANIZATION_ID,
                slug="test-org",
                public_name="Test Organization",
                status="verified",
            )
        )
    yield
    Base.metadata.drop_all(bind=test_engine)


@event.listens_for(Session, "before_flush")
def _belong_to_the_test_organization(session, _flush_context, _instances):
    """Give every new row the test organization, unless it has one.

    Courses, cohorts, invitations and grade sheets carry a NOT NULL
    ``organization_id`` from 2026-08-27. Several hundred tests create
    them directly and none of them are about organizations; making each
    one name a column it does not care about would bury what those tests
    actually say.

    This is test infrastructure and deliberately not a model default: in
    production the column has no default, so a code path that forgets it
    fails loudly instead of quietly filing a course under whichever
    organization happened to be first.
    """
    for obj in session.new:
        if hasattr(obj, "organization_id") and getattr(obj, "organization_id", None) is None:
            obj.organization_id = TEST_ORGANIZATION_ID


#: ``session.info`` key: set to switch the acceptance autopopulator below off.
NOBODY_HAS_SIGNED_ANYTHING = "nobody_has_signed_anything"


@pytest.fixture()
def nobody_has_signed_anything(db: Session) -> None:
    """Make this test's session create users who have accepted nothing.

    For the tests of the consent gate itself, and of the acceptance record:
    a person who has not signed must actually not have signed, or the thing
    under test is seeded out of existence.
    """
    db.info[NOBODY_HAS_SIGNED_ANYTHING] = True


@event.listens_for(Session, "after_flush")
def _everybody_in_the_tests_has_already_signed(session, _flush_context):
    """Give every new user the acceptances the API now insists on.

    From 2026-09-17 a signed-in person who has not accepted the current
    documents is refused every POST/PUT/PATCH/DELETE (see
    ``app.api.consent_gate``). That is the point of the gate, and it means
    several hundred tests that create a user and then write something would
    all fail on a consent screen none of them are about.

    In production a person signs before they can act, so the faithful thing
    for a fabricated profile is to arrive already signed — the same shape the
    e2e suite gets from ``scripts/seed_e2e_legal_acceptance.py``. Test
    infrastructure, like the organization and course autopopulators above,
    and deliberately not a model default: production has none, so a code path
    that skips the gate fails loudly rather than being quietly forgiven.

    Every signable slug at its current version, regardless of role: the
    registry decides which of them a given role is actually asked for, and
    holding a row for one it is not asked for changes no answer.

    ``after_flush`` rather than ``before_flush``, and a Core insert rather
    than ``session.add``: the acceptance carries a foreign key to the profile,
    and adding both in one flush leaves the order to the unit of work, which
    sorts on relationships — and there is no relationship between these two,
    only a column. It put the child first, and SQLite said so.
    """
    if session.info.get(NOBODY_HAS_SIGNED_ANYTHING):
        return
    rows = [
        {
            "user_id": obj.id,
            "document_slug": slug,
            "version": version,
            "locale": "en",
            "content_sha256": "seeded-by-the-test-suite",
        }
        for obj in session.new
        if isinstance(obj, User) and obj.id is not None
        for slug, version in LEGAL_DOCUMENTS.items()
    ]
    if rows:
        session.execute(LegalAcceptance.__table__.insert(), rows)


#: ``session.info`` key: set to switch the chapter autopopulator below off.
CHAPTERS_NAME_THEIR_OWN_COURSE = "chapters_name_their_own_course"


@pytest.fixture()
def chapters_name_their_own_course(db: Session) -> None:
    """Make this test's session refuse to fill ``Chapter.course_id`` in.

    For the tests of the production write paths (``create_chapter``,
    ``clone_course``, the chapter route): a path that forgot the column must
    hit the NOT NULL, not be quietly corrected by the listener below.
    """
    db.info[CHAPTERS_NAME_THEIR_OWN_COURSE] = True


@event.listens_for(Session, "before_flush")
def _a_chapter_belongs_to_its_module_s_course(session, _flush_context, _instances):
    """Give every new chapter the course of its module, unless it names one.

    ``chapters.course_id`` is NOT NULL from 2026-09-07 and always equals
    the module's ``course_id``; the production write paths set both.
    Sixty-odd test builders predate the column and say only ``module_id``
    — they are about grading, progress and readiness, not about which
    parents a chapter carries — so the column is filled in here from the
    module, which may itself still be pending in this very flush (looked
    up in ``session.new`` before the database) and may know its course
    only through the ``course`` relationship (its own FK is filled later
    in the same flush).

    Test infrastructure, like the organization above, and for the same
    reason not a model default. The tests of the write paths themselves
    switch it off (``chapters_name_their_own_course``), or they would prove
    nothing.
    """
    if session.info.get(CHAPTERS_NAME_THEIR_OWN_COURSE):
        return
    pending_modules = {obj.id: obj for obj in session.new if isinstance(obj, Module)}
    for obj in session.new:
        if not isinstance(obj, Chapter) or obj.course_id is not None or obj.course is not None:
            continue
        module = obj.module or pending_modules.get(obj.module_id)
        if module is None and obj.module_id is not None:
            with session.no_autoflush:
                module = session.get(Module, obj.module_id)
        if module is None:
            continue
        if module.course_id is not None:
            obj.course_id = module.course_id
        elif module.course is not None:
            obj.course = module.course


@pytest.fixture(autouse=True)
def _disable_translation(monkeypatch: pytest.MonkeyPatch):
    """Default-disable the Gemini translation pipeline for every test.

    Without this, any test that touches a write hook calling
    ``run_course_translation_pipeline_if_published`` /
    ``reconcile_entity_if_course_published`` will (a) try to hit the
    real Gemini API if ``GEMINI_API_KEY`` is set in the CI environment
    and (b) flake with HTTP 429 quota errors when the dev key's daily
    cap is exhausted.

    We unset both the env var AND ``settings.GEMINI_API_KEY`` so
    ``is_translation_enabled()`` returns False through its natural
    code path. Tests that DO want real translation (e.g.
    ``test_translation_orchestrator.py``) re-enable it explicitly via
    their own ``monkeypatch.setattr(settings.GEMINI_API_KEY, ...)``,
    and that re-enable wins because their fixture runs second.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        None,
        raising=False,
    )


@pytest.fixture(autouse=True)
def _restore_dependency_overrides():
    """Give every test back the dependency overrides it started with.

    A test that swaps ``get_current_user`` to check a permission
    boundary, then fails its assertion, never reaches its own cleanup —
    and every test after it in that file runs authenticated as somebody
    else. That is how an order-dependent suite is born: the failure
    surfaces three files later, in a test that is not wrong.

    Snapshot-and-restore rather than ``clear()``: the client fixtures
    install their own overrides, and clearing would pull them out from
    under a test that is still running.
    """
    from app.main import app

    snapshot = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(snapshot)


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


@pytest.fixture
def two_locales(monkeypatch: pytest.MonkeyPatch):
    """Run a test against the ``ru`` + ``en`` set.

    Several suites describe how a mechanism behaves — how many rows a
    translation writes, how many provider calls a publish costs — and
    counted those against the live ``LOCALE_CODES``. That made them
    quietly change meaning the day German and Ukrainian were switched
    on: the mechanism was fine, the arithmetic was not.

    The number of languages is a parameter of those tests, so this
    fixture states it. Tests that are *about* the wider set say so
    themselves.

    ``LOCALE_CODES`` is imported by name into a dozen modules, so this
    patches every module that holds a reference rather than the one
    definition.
    """
    import sys

    for module in list(sys.modules.values()):
        name = getattr(module, "__name__", "")
        if name.startswith("app.") and hasattr(module, "LOCALE_CODES"):
            monkeypatch.setattr(module, "LOCALE_CODES", ("ru", "en"), raising=False)
