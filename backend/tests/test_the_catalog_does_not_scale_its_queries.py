"""The catalog costs the same number of database round-trips at any size.

A catalog page is one request, and its cost should be a property of the
page, not of how many courses the school has published. This file pins
that, because the property was quietly lost once already.

``_COURSE_LIST_TREE`` deliberately stopped at the module level, on the
reasoning that a card only needs ``course.modules?.length``. Later the
card grew a localized tree, and ``build_localized_course_summaries``
started reading ``module.chapters`` — twice, and serialising them into
the response. Nothing failed. Each module simply became its own lazy
SELECT: five courses of three modules cost 24 round-trips, 15 of them
chapter loads. Production runs 47 modules, in ``iad1``, against a
database in ``us-west-2`` — every one of those queries paid for a
cross-country round-trip, and ``GET /api/v1/courses`` answered in
2.4-2.9 seconds while ``/health`` answered in two milliseconds.

Counting queries is the only assertion that catches this. A response
test passes either way — the payload is identical; only the cost
changes. So this test counts, and it compares two sizes rather than
pinning one number, because the failure mode is *growth*: a loader that
went back to lazy-loading would still pass a single-size assertion after
somebody updated the constant to match.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import event

from app.models.content_version import ContentVersion
from app.models.course import Course, Module
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

_MODULES_PER_COURSE = 3
_CHAPTERS_PER_MODULE = 2


def _publish_courses(db: Session, count: int) -> None:
    """``count`` published courses, each a small module/chapter tree."""
    from app.models.course import Chapter

    for i in range(count):
        course_id = f"catalog-cost-{uuid.uuid4().hex[:8]}"
        db.add(
            Course(
                id=course_id,
                status="published",
                access_mode="public",
                created_by=ADMIN_ID,
                source_locale="ru",
                organization_id=TEST_ORGANIZATION_ID,
            )
        )
        for field, text in (("title", f"Course {i}"), ("description", f"Description {i}")):
            db.add(
                ContentVersion(
                    entity_type="course",
                    entity_id=course_id,
                    field=field,
                    locale="ru",
                    text=text,
                    origin="human",
                    status="ok",
                )
            )
        for m in range(_MODULES_PER_COURSE):
            module_id = str(uuid.uuid4())
            db.add(Module(id=module_id, course_id=course_id, order_index=m))
            for c in range(_CHAPTERS_PER_MODULE):
                db.add(
                    Chapter(
                        id=str(uuid.uuid4()),
                        module_id=module_id,
                        course_id=course_id,
                        title=f"Lesson {c}",
                        order_index=c,
                    )
                )
    db.commit()


def _round_trips_for_catalog(db: Session, client: TestClient) -> int:
    """How many statements the database is asked for by one catalog request."""
    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    try:
        response = client.get("/api/v1/courses", headers={"Accept-Language": "en"})
        assert response.status_code == 200, response.text
    finally:
        event.remove(engine, "before_cursor_execute", _record)
    return len(statements)


def test_the_catalog_costs_the_same_at_one_course_and_at_five(
    db: Session, client: TestClient, admin: User, teacher: User
) -> None:
    _publish_courses(db, 1)
    one_course = _round_trips_for_catalog(db, client)

    _publish_courses(db, 4)
    five_courses = _round_trips_for_catalog(db, client)

    assert five_courses == one_course, (
        f"the catalog cost {one_course} queries for one course and {five_courses} for five — "
        "something in the page is loading per course or per module again"
    )


def test_the_catalog_still_serves_the_whole_tree(db: Session, client: TestClient, admin: User, teacher: User) -> None:
    """The cheap loader must not have become a loader that drops data.

    Loading less is only correct while the response is unchanged — and the
    response does carry every module and every chapter.
    """
    _publish_courses(db, 1)

    body = client.get("/api/v1/courses", headers={"Accept-Language": "en"}).json()

    assert len(body) == 1
    modules = body[0]["modules"]
    assert len(modules) == _MODULES_PER_COURSE
    assert [len(module["chapters"]) for module in modules] == [_CHAPTERS_PER_MODULE] * _MODULES_PER_COURSE
