"""Render a course to PDF (outline + chapter content).

The PDF is generated server-side with reportlab Platypus. Output is a
clean, printable course handout — useful for archival, offline
reading, and as a marketing artefact (a school can hand the PDF to a
pastor as a sample of what the platform produces).

The document follows the course's own chapter order. A chapter
belongs to its course; a module is an optional grouping, so the walk
is over ``course.chapters`` (course-global ``order_index``) and the
module is consulted only for the heading it contributes. A course
with no modules at all prints as a flat list of lessons, with no
group headings anywhere — not with empty ones.

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


def _group_of(chapter: Chapter, live_modules: dict[str, Module]) -> str | None:
    """The id of the module that groups this chapter, or ``None``.

    ``None`` covers both a chapter that never had a module and one whose
    module is not in the course's live list. The second case is the one
    worth naming: ``delete_module`` detaches live chapters as it bins the
    module, but a row that predates that rule can still point at a binned
    module. The lesson is live either way, so it prints — ungrouped,
    rather than under a heading the course no longer has.
    """
    module_id = getattr(chapter, "module_id", None)
    if module_id is None:
        return None
    key = str(module_id)
    return key if key in live_modules else None


def build_course_outline(course: Course) -> list[CourseSection]:
    """Split the course's chapters into the runs the document prints.

    The walk is over ``course.chapters`` — every lesson of the course, in
    the course-global ``order_index`` the write path maintains — and not
    over ``course.modules``, which is what used to drop a module-less
    lesson from the export entirely: no error, no empty page, just a
    course missing a piece that only its author would miss.

    A module keeps its lessons together and takes the position of its
    first one, so a course whose modules already run consecutively (every
    course built through the editor) prints exactly as it did before. An
    ungrouped lesson sits where its own ``order_index`` puts it, which is
    the same rule the rest of the course order obeys — the module is a
    label on a run of lessons, not a tier above them.

    A module with no live chapters yields no section at all, so it cannot
    leave an empty rubric behind.
    """
    live_modules = {str(module.id): module for module in (course.modules or [])}
    chapters = list(course.chapters or [])

    by_group: dict[str, list[Chapter]] = {}
    for chapter in chapters:
        group = _group_of(chapter, live_modules)
        if group is not None:
            by_group.setdefault(group, []).append(chapter)

    sections: list[CourseSection] = []
    emitted: set[str] = set()
    for chapter in chapters:
        group = _group_of(chapter, live_modules)
        if group is None:
            # Consecutive ungrouped lessons share one section: they carry
            # no heading, so splitting them would only scatter a flat
            # course over one page per lesson.
            if sections and sections[-1].module is None:
                sections[-1].chapters.append(chapter)
            else:
                sections.append(CourseSection(module=None, chapters=[chapter]))
            continue
        if group in emitted:
            continue
        emitted.add(group)
        sections.append(CourseSection(module=live_modules[group], chapters=by_group[group]))
    return sections


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
