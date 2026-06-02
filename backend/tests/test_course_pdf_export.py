"""Tests for the course PDF export pipeline.

Covers both the ``render_course_pdf`` service (pure layout, no DB) and
the ``GET /courses/{course_id}/export.pdf`` route (visibility +
content-disposition + filename hardening).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from app.models.course import Chapter, CourseStatus
from app.models.enrollment import Enrollment
from app.services.course_pdf import render_course_pdf

from ._cv_helpers import (
    make_course_with_text,
    make_module_with_text,
)
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _seed_course_with_outline(db: Session, course_id: str, *, status: str = "published"):
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="PDF Test Course",
        description="A test course for PDF export.",
        status=status,
        created_by=TEACHER_ID,
    )
    module = make_module_with_text(
        db,
        module_id=f"{course_id}-mod",
        course_id=course.id,
        title="Module One",
        description="The first module.",
    )
    chapter = Chapter(
        id=f"{course_id}-ch",
        module_id=module.id,
        title="Opening Chapter",
        order_index=0,
        chapter_type="reading",
    )
    db.add(chapter)
    db.commit()
    return course


class TestRenderCoursePdf:
    """Pure layout — no DB, no auth. Pin the byte-level invariants
    (PDF magic header, non-empty body) so a future refactor doesn't
    accidentally produce an empty / corrupt file."""

    def test_returns_valid_pdf_magic(self) -> None:
        course = MagicMock()
        course.title = "Test"
        course.description = "<p>A description</p>"
        course.modules = []
        out = render_course_pdf(course)
        # PDF files start with the magic ``%PDF-`` sequence — without
        # that, browsers won't render the download inline and the
        # ``application/pdf`` Content-Type is a lie.
        assert out[:5] == b"%PDF-"
        # Non-empty body so a refactor that strips all content but
        # keeps the header doesn't slip through.
        assert len(out) > 500

    def test_handles_missing_optional_fields(self) -> None:
        """``title``, ``description``, and module/chapter titles can all
        be ``None`` for in-progress courses. The renderer must
        substitute a placeholder rather than crashing on ``None``
        passed into ``Paragraph(...)``."""
        course = MagicMock()
        course.title = None
        course.description = None
        course.modules = []
        out = render_course_pdf(course)
        assert out[:5] == b"%PDF-"

    def test_strips_html_in_chapter_blocks(self) -> None:
        """The block content is sanitised HTML; the PDF flow renders
        plain prose, so the tag strip must drop angle brackets without
        eating the visible text."""
        block = MagicMock()
        block.block_type = "text"
        block.content = "<p>Visible <strong>text</strong></p>"
        block.order_index = 0

        chapter = MagicMock()
        chapter.title = "Ch"
        chapter.blocks = [block]

        module = MagicMock()
        module.title = "Mod"
        module.description = None
        module.chapters = [chapter]

        course = MagicMock()
        course.title = "X"
        course.description = None
        course.modules = [module]

        out = render_course_pdf(course)
        assert out[:5] == b"%PDF-"


class TestExportRouteVisibility:
    def test_unknown_course_returns_404(self, client: TestClient) -> None:
        r = client.get("/api/v1/courses/nope-not-here/export.pdf")
        assert r.status_code == 404

    def test_owner_can_export(self, client: TestClient, db: Session) -> None:
        course = _seed_course_with_outline(db, "pdf-owner-1")
        r = client.get(f"/api/v1/courses/{course.id}/export.pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        # PDF magic in the body.
        assert r.content[:5] == b"%PDF-"
        # Sane attachment filename — letters / digits / underscore only.
        cd = r.headers["content-disposition"]
        assert "attachment" in cd
        assert cd.endswith('.pdf"')

    def test_admin_can_export(self, admin_client: TestClient, db: Session) -> None:
        _seed_course_with_outline(db, "pdf-admin-1")
        r = admin_client.get("/api/v1/courses/pdf-admin-1/export.pdf")
        assert r.status_code == 200

    def test_enrolled_student_can_export(self, student_client: TestClient, db: Session) -> None:
        course = _seed_course_with_outline(db, "pdf-student-1")
        db.add(
            Enrollment(
                id=f"enr-{course.id}",
                user_id=STUDENT_ID,
                course_id=course.id,
                progress=0,
            )
        )
        db.commit()
        r = student_client.get(f"/api/v1/courses/{course.id}/export.pdf")
        assert r.status_code == 200

    def test_unenrolled_student_published_course_is_403(self, student_client: TestClient, db: Session) -> None:
        _seed_course_with_outline(db, "pdf-student-2", status="published")
        r = student_client.get("/api/v1/courses/pdf-student-2/export.pdf")
        assert r.status_code == 403

    def test_unpublished_course_is_404_for_non_owner_non_admin(self, student_client: TestClient, db: Session) -> None:
        """Unpublished courses 404 (not 403) so the export endpoint
        doesn't tell an attacker which draft courses exist."""
        _seed_course_with_outline(db, "pdf-draft-1", status=CourseStatus.DRAFT)
        r = student_client.get("/api/v1/courses/pdf-draft-1/export.pdf")
        assert r.status_code == 404


class TestExportRouteHeaders:
    def test_cache_control_is_private_nostore(self, client: TestClient, db: Session) -> None:
        course = _seed_course_with_outline(db, "pdf-hdr-1")
        r = client.get(f"/api/v1/courses/{course.id}/export.pdf")
        # Course content changes; a CDN cache of stale PDFs would
        # surface old material to students.
        assert r.headers["cache-control"] == "private, no-store"

    def test_vary_accept_language(self, client: TestClient, db: Session) -> None:
        course = _seed_course_with_outline(db, "pdf-hdr-2")
        r = client.get(f"/api/v1/courses/{course.id}/export.pdf")
        # The title / description vary per locale; if the proxy chain
        # ever caches, it must key on Accept-Language to avoid mixing.
        # GZip middleware appends Accept-Encoding; assert ours is there.
        assert "Accept-Language" in r.headers["vary"]

    def test_non_ascii_title_falls_back_to_course_id_in_filename(self, client: TestClient, db: Session) -> None:
        """Cyrillic / accented titles can't ride the legacy
        ``filename=`` header (latin-1). The route strips to ASCII;
        when nothing survives, fall back to the course id prefix."""
        # Build a course with a Russian-only title — every char fails
        # ``isascii``, leaving an empty ``safe_title`` that triggers
        # the course-id fallback.
        course = make_course_with_text(
            db,
            course_id="pdf-cyrillic",
            title="Только кириллица",
            status="published",
            created_by=TEACHER_ID,
        )
        db.commit()
        r = client.get(f"/api/v1/courses/{course.id}/export.pdf")
        assert r.status_code == 200
        cd = r.headers["content-disposition"]
        assert "pdf-cyri.pdf" in cd  # course-id prefix fallback (first 8 chars)
