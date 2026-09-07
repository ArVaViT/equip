"""Render a course to PDF (outline + chapter content).

The PDF is generated server-side with reportlab Platypus. Output is a
clean, printable course handout — useful for archival, offline
reading, and as a marketing artefact (a school can hand the PDF to a
pastor as a sample of what the platform produces).

The document follows the course's own reading order, and does not
decide it: ``course_structure.build_spine`` does, for this and for
every other surface that walks a course. A course with no modules at
all prints as a flat list of lessons, with no group headings
anywhere — not with empty ones.

Scope of this first iteration:

* Title page with course title + brief description.
* Outline (table of contents shape) — group headings where a module
  groups something, lesson lines at the course level where nothing does.
* Per-chapter section with chapter title and rendered text blocks
  (HTML stripped to plain prose for now — rich rendering follows in
  a later iteration if there's demand).

Out of scope (deliberate):

* Embedded images / videos / audio (would balloon file size).
* Quiz / assignment rendering (no test-paper format yet).
* Multi-locale switch (whoever fetches the PDF gets the source
  locale; the route honours ``Accept-Language`` so the picker is
  applied before content reaches this module).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.sanitize import html_to_plain_text
from app.services.course_structure import build_spine

if TYPE_CHECKING:
    from reportlab.lib.styles import ParagraphStyle

    from app.models.course import Chapter, Course, Module


def _to_plain_text(html: str | None) -> str:
    """Collapse HTML to clean prose for the PDF.

    One shared implementation in ``core.sanitize`` — the same job the
    verse card and the scripture comparison were each doing with their
    own copy of the same regex.
    """
    return html_to_plain_text(html)


@dataclass
class CourseSection:
    """One run of the document: a module and its lessons, or a run of
    lessons no module groups.

    ``module`` is ``None`` for the ungrouped run, and the renderer prints
    no heading for it — a lesson that belongs straight to the course sits
    under the course, not under an invented rubric.
    """

    module: Module | None
    chapters: list[Chapter] = field(default_factory=list)


def build_course_outline(course: Course) -> list[CourseSection]:
    """Split the course's chapters into the runs the document prints.

    The order is not this module's to decide: it comes from
    :func:`~app.services.course_structure.build_spine`, the one function
    the readiness checklist and the teacher's board read too. The export
    used to walk ``course.modules``, which dropped a module-less lesson
    from the document entirely — no error, no empty page, just a course
    missing a piece only its author would miss — and then walked
    ``course.chapters`` flat, which printed the headings of every live
    course in an order nobody had authored, because lesson numbers ran
    per module and every module started at zero.

    A module with no live chapters yields no section at all, so it cannot
    leave an empty rubric behind; the spine still carries it, for the
    surfaces that show a teacher the heading they made.
    """
    spine = build_spine(list(course.modules or []), list(course.chapters or []))
    return [CourseSection(module=run.module, chapters=list(run.chapters)) for run in spine.runs if run.chapters]


def _build_styles() -> dict[str, ParagraphStyle]:
    # function-level: keeps reportlab (~100ms) out of serverless cold start
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}
    styles["title"] = ParagraphStyle(
        "EquipTitle",
        parent=base["Title"],
        fontName="Helvetica-Bold",
        fontSize=28,
        leading=34,
        alignment=1,  # TA_CENTER
        spaceAfter=12,
    )
    styles["subtitle"] = ParagraphStyle(
        "EquipSubtitle",
        parent=base["Italic"],
        fontSize=12,
        leading=16,
        alignment=1,
        spaceAfter=30,
    )
    styles["heading_module"] = ParagraphStyle(
        "ModuleHeading",
        parent=base["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        spaceBefore=18,
        spaceAfter=8,
    )
    styles["heading_chapter"] = ParagraphStyle(
        "ChapterHeading",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        spaceBefore=12,
        spaceAfter=6,
    )
    styles["body"] = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontSize=11,
        leading=15,
        spaceAfter=6,
    )
    # Three outline levels, because the outline now has three things to
    # say. A module line is a group heading (bold, flush left); a lesson
    # inside it is indented under it; a lesson the course holds directly
    # is flush left but not bold — it is a lesson, not a group, and at
    # one weight for both the reader could not tell which is which.
    styles["toc_module"] = ParagraphStyle(
        "TocModule",
        parent=base["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=15,
        spaceBefore=6,
    )
    styles["toc_entry"] = ParagraphStyle(
        "TocEntry",
        parent=base["BodyText"],
        fontSize=11,
        leading=15,
        leftIndent=20,
    )
    styles["toc_chapter"] = ParagraphStyle(
        "TocChapter",
        parent=base["BodyText"],
        fontSize=11,
        leading=15,
    )
    styles["footer"] = ParagraphStyle(
        "Footer",
        parent=base["Italic"],
        fontSize=9,
        textColor=(0.5, 0.5, 0.5),
    )
    return styles


def render_course_pdf(course: Course) -> bytes:
    """Return the PDF bytes for the given hydrated course.

    Caller is responsible for hydrating the course's title /
    description / module-tree at the requested locale BEFORE handing
    it in. This function is pure layout — no DB access, no locale
    resolution, no permission checks.
    """
    # function-level: keeps reportlab (~100ms) out of serverless cold start
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        # The PDF metadata title, not a heading: a document with no
        # title at all confuses a file manager, and the brand is the one
        # word that reads the same in every language served.
        title=course.title or "Equip",
        author="Equip",
    )
    styles = _build_styles()
    story: list = []

    # Title page.
    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph(course.title or "", styles["title"]))
    if course.description:
        story.append(Paragraph(_to_plain_text(course.description), styles["subtitle"]))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph("Generated by Equip", styles["footer"]))
    story.append(PageBreak())

    sections = build_course_outline(course)

    # Table of contents. A course with nothing in it yet gets no
    # "Contents" page — the same rule that keeps a module without lessons
    # from printing a heading over nothing.
    if sections:
        story.append(Paragraph("Contents", styles["heading_module"]))
        for section in sections:
            if section.module is not None:
                story.append(Paragraph(section.module.title or "", styles["toc_module"]))
            entry_style = styles["toc_entry"] if section.module is not None else styles["toc_chapter"]
            for chapter in section.chapters:
                story.append(Paragraph(chapter.title or "", entry_style))
        story.append(PageBreak())

    # Body, section by section. The page break goes between sections
    # rather than after each, so the document ends on its last lesson.
    for index, section in enumerate(sections):
        if index:
            story.append(PageBreak())
        if section.module is not None:
            story.append(Paragraph(section.module.title or "", styles["heading_module"]))
            if section.module.description:
                story.append(Paragraph(_to_plain_text(section.module.description), styles["body"]))
        for chapter in section.chapters:
            story.append(Paragraph(chapter.title or "", styles["heading_chapter"]))
            # Render any text blocks the chapter carries. We sort by
            # ``order_index`` so the printed sequence matches the
            # student-facing chapter view.
            blocks = sorted(
                (b for b in (getattr(chapter, "blocks", None) or []) if getattr(b, "block_type", "") == "text"),
                key=lambda b: getattr(b, "order_index", 0),
            )
            for block in blocks:
                content = getattr(block, "content", None) or ""
                plain = _to_plain_text(content)
                if plain:
                    story.append(Paragraph(plain, styles["body"]))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


__all__ = ["CourseSection", "build_course_outline", "render_course_pdf"]
