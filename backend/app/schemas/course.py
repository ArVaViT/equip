from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas._media_url import validate_safe_media_url
from app.schemas._request import RequestModel

# Mirrors the ``chapters_chapter_type_check`` CHECK in Postgres. ``video`` /
# ``audio`` / ``mixed`` / ``content`` were collapsed into block-based
# ``reading`` by migration 024 — block rows carry the content shape instead.
CHAPTER_TYPES = Literal["reading", "quiz", "exam", "assignment"]


class ChapterBase(RequestModel):
    title: str = Field(..., min_length=1, max_length=300)
    order_index: int = 0
    chapter_type: CHAPTER_TYPES = "reading"
    requires_completion: bool = False
    is_locked: bool = False


class ChapterCreate(ChapterBase):
    pass


class ChapterUpdate(RequestModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    order_index: int | None = None
    chapter_type: CHAPTER_TYPES | None = None
    requires_completion: bool | None = None
    is_locked: bool | None = None
    #: Move the lesson between groups: a module id puts it under that
    #: heading, ``null`` takes it out and leaves it in the course.
    #:
    #: This is the field a teacher reaches for when they got the
    #: structure wrong the first time, which is the common case and the
    #: reason the whole move exists. The route checks that the module
    #: belongs to the same course — a chapter may be regrouped, never
    #: rehomed into somebody else's course.
    #:
    #: ``None`` here is a real value ("no module"), not "unchanged":
    #: ``update_chapter`` patches by ``exclude_unset``, so a body that
    #: omits the key leaves the grouping alone.
    module_id: str | None = None


class ChapterResponse(ChapterBase):
    # ``extra`` back to the permissive default: the request base forbids
    # unknown keys, and this model is built from an ORM row, not a body.
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    # A lesson the reader's language does not have yet resolves to "".
    # The constraint on ``ChapterBase.title`` belongs to what a teacher
    # submits, not to what a reader receives. See ``_ReadTitle``.
    title: str = ""
    id: str
    # Optional on the wire from 2026-09-07: a chapter belongs to its
    # course, and a module is a grouping it may not have. Every chapter
    # production serves today still names one; the type is widened ahead
    # of the column so the first chapter without a module serialises
    # instead of failing (or, worse, arriving as the string "None").
    module_id: str | None
    course_id: str


class ChapterSummary(BaseModel):
    """Chapter fields for list responses — identical to ``ChapterResponse``
    now that no body content lives on the chapter row. Kept as a separate
    type so future slimming (e.g. dropping ``chapter_type``) is easy."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    # Optional for the same reason as on ``ChapterResponse``: a chapter
    # belongs to its course and may have no module. This one lagged
    # behind — a required ``str`` here cannot represent a module-less
    # chapter at all, so any list response that grew one would raise
    # instead of serialising it.
    module_id: str | None
    course_id: str
    title: str = ""
    order_index: int = 0
    chapter_type: CHAPTER_TYPES = "reading"
    requires_completion: bool = False
    is_locked: bool = False


class ModuleBase(RequestModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    order_index: int = 0
    due_date: datetime | None = None


class ModuleCreate(ModuleBase):
    pass


class ModuleUpdate(RequestModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000)
    order_index: int | None = None
    due_date: datetime | None = None


class ModuleResponse(ModuleBase):
    # ``extra`` back to the permissive default: the request base forbids
    # unknown keys, and this model is built from an ORM row, not a body.
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    title: str = ""
    id: str
    course_id: str
    chapters: list[ChapterResponse] = Field(default_factory=list)


class ModuleSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    title: str = ""
    description: str | None = None
    order_index: int = 0
    due_date: datetime | None = None
    chapters: list[ChapterSummary] = []


class CourseBase(RequestModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = Field(None, max_length=10_000)
    image_url: str | None = Field(None, max_length=2048)


class _ReadTitle(BaseModel):
    """A title on the way out, which may be a title this reader does not have.

    ``CourseBase`` constrains ``title`` to at least one character, and
    that is right for what a teacher submits. It is wrong for what a
    reader receives: since the spare language was removed, a course with
    no row in the reader's language resolves to ``""`` — and a required
    non-empty field turned that into a 500 on the catalog for every
    German and Ukrainian visitor, which is how this was found.

    Read models carry the field without the length rule and let the
    client say "not translated yet".
    """

    title: str = ""
    description: str | None = Field(None, max_length=10_000)
    image_url: str | None = Field(None, max_length=2048)


class CourseCreate(CourseBase):
    # Validate the inherited image_url on INPUT only (CourseResponse also
    # inherits CourseBase but defines no validator, so reads of any
    # legacy value are never rejected).
    @field_validator("image_url")
    @classmethod
    def _validate_image_url(cls, value: str | None) -> str | None:
        return validate_safe_media_url(value)


class CourseUpdate(RequestModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = Field(None, max_length=10_000)
    image_url: str | None = Field(None, max_length=2048)
    status: Literal["draft", "published"] | None = None
    # ADR-010: course access mode controls who can ENROLL (public allows
    # solo self-enroll; institute is admin-invite only). Only admins should
    # PATCH this — the route's permission check enforces that.
    access_mode: Literal["public", "institute"] | None = None
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None

    @field_validator("image_url")
    @classmethod
    def _validate_image_url(cls, value: str | None) -> str | None:
        return validate_safe_media_url(value)


class CourseResponse(_ReadTitle):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str = "draft"
    # Controls the enroll button on the catalog: ``public`` shows
    # "Записаться", ``institute`` shows "Доступно только по приглашению".
    access_mode: Literal["public", "institute"] = "public"
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None
    modules: list[ModuleResponse] = []
    #: The course's chapters that no module groups.
    #:
    #: New on 2026-09-07, when a chapter stopped needing a module. Such
    #: a chapter has no place in ``modules[].chapters`` and without this
    #: field would not reach the client at all — the lesson would exist,
    #: be gradable, be counted in denominators, and be invisible.
    #:
    #: Deliberately **not** every chapter of the course, though the ORM
    #: relationship behind it (``Course.chapters``) is exactly that.
    #: ``modules[].chapters`` already carries the grouped ones and is
    #: what every reader walks today; repeating them here would put each
    #: grouped chapter in one payload twice, and anything summing the
    #: two lists — a "N lessons" label, a progress denominator — would
    #: count it twice. The two lists are a partition instead:
    #: concatenate them and every live chapter appears exactly once.
    #:
    #: The validator below enforces that rather than trusting callers,
    #: because ``CourseResponse.model_validate(course, from_attributes=True)``
    #: — the ``?source=1`` editor path and the no-overlay path both take
    #: it — reads the relationship whole.
    chapters: list[ChapterResponse] = []

    @field_validator("chapters", mode="after")
    @classmethod
    def _only_chapters_no_module_groups(cls, value: list[ChapterResponse]) -> list[ChapterResponse]:
        return [chapter for chapter in value if chapter.module_id is None]


class CourseSummary(_ReadTitle):
    """Catalog / list-view course. Kept as a separate shape from
    ``CourseResponse`` so that if we later decide to, say, omit modules/
    chapters from list responses entirely, we can do that in one place.

    No course-level ``chapters`` here, unlike ``CourseResponse``. The
    list loader (``_COURSE_LIST_TREE``) fetches modules and stops, on
    purpose — a catalog page of 10 courses would otherwise carry every
    chapter of every course — and a field this loader never fills would
    report "no loose lessons" for a course that has them, which is worse
    than not answering. The list surfaces render a module count and a
    title; nothing there reads a chapter. The course detail view
    (``GET /courses/{id}``) is where the tree is served.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    #: Who is teaching this. The plain answer to the question a reader
    #: asks before enrolling, and the thing that makes ``public_name``
    #: worth defending — a name nobody sees is not a name anyone can
    #: misuse or protect.
    #:
    #: Optional in the shape though ``courses.organization_id`` is NOT
    #: NULL: the resolver leaves it unset rather than inventing a name
    #: if the organization row is somehow not there, and a card with a
    #: missing school is better than a card with a borrowed one.
    organization_name: str | None = None
    organization_slug: str | None = None
    status: str = "draft"
    access_mode: Literal["public", "institute"] = "public"
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None
    modules: list[ModuleSummary] = []


class EnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: UUID
    course_id: str
    cohort_id: UUID | None = None
    enrolled_at: datetime
    progress: int
    course: CourseResponse | None = None


class CourseDashboardSummary(_ReadTitle):
    """Course shape for the student-dashboard list (``/users/me/courses``).

    Deliberately omits ``modules`` (and therefore the chapter level): the
    dashboard renders only the course title + the enrollment's progress, and
    no ``getMyCourses`` consumer reads ``course.modules``. Keeping this shape
    free of the module/chapter relationship lets the loader skip the tree
    entirely — no eager full-tree fetch, no per-module lazy-load on serialise.
    See ``course_service.get_user_courses``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str = "draft"
    access_mode: Literal["public", "institute"] = "public"
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    enrollment_start: datetime | None = None
    enrollment_end: datetime | None = None


class EnrollmentSummaryResponse(BaseModel):
    """Enrollment for the dashboard list — embeds the slim CourseDashboardSummary.

    ``progress`` is assessment-only by design (see
    ``course_service.sync_enrollment_progress``). ``chapters_read`` /
    ``chapters_to_read`` carry the other half of the story, because the
    dashboard used to show the percentage alone: a student who had read
    every lesson of a 16-chapter course and not yet sat a quiz was told 0%,
    which is true about assessment and false about the student.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: UUID
    course_id: str
    cohort_id: UUID | None = None
    enrolled_at: datetime
    progress: int
    chapters_read: int = 0
    chapters_to_read: int = 0
    course: CourseDashboardSummary | None = None


class CourseTranslationResponse(BaseModel):
    """Summary returned by the manual ``POST /courses/{id}/translate`` hook.

    Mirrors ``OrchestratorReport`` from the translation service so the
    teacher UI can show "X translated, Y skipped, Z failed" without having
    to re-shape the payload on the client.

    ``queued`` means the work was handed to the worker rather than done
    inside the request — the counters are then zero because nothing has
    happened yet, and the caller should poll
    ``GET /courses/{id}/translation-progress``.
    """

    translated: int = 0
    skipped: int = 0
    failed: int = 0
    enabled: bool = True
    queued: bool = False


class TranslationGapSummary(BaseModel):
    """Why a course is not ready, in the three shapes that need different
    work from a person: waiting, reading, retrying."""

    missing: int = 0
    needs_review: int = 0
    failed: int = 0


class CourseTranslationProgress(BaseModel):
    """How far along a course is toward being servable in every language.

    What the teacher's "prepare for publication" panel renders, and what
    the publish button reads to decide whether it can be enabled. The
    counts are (field, locale) pairs — the same unit the publication gate
    itself uses, so the number on screen and the decision agree.
    """

    course_id: str
    status: str
    required: int
    present: int
    is_complete: bool
    #: Remaining work per language, so "German is 12 behind" is visible
    #: rather than one aggregate that hides which audience is waiting.
    by_locale: dict[str, int] = {}
    gaps: TranslationGapSummary = TranslationGapSummary()
    #: Edits to a live course that are held until every language has them.
    #: Non-zero only for a published course being edited.
    held_edits: int = 0
    #: Held edits that will not resolve on their own — a translation came
    #: back and failed its check. These need a person, and silence about
    #: them reads to the teacher as an edit that did nothing.
    blocked_edits: int = 0
    #: False when no provider is configured (local dev, a deploy without
    #: a key). Nothing will translate, and the gate does not block.
    enabled: bool = True
    #: Why the course is not whole yet, as one word the card can put
    #: into a sentence. ``needs_review`` — translations came back and a
    #: person has to read them before they are served; nothing the
    #: teacher does moves them. ``failed_permanent`` — the pipeline gave
    #: up on them after five attempts and an admin has to re-queue them.
    #: ``translating`` — the pipeline has simply not got there yet.
    #: ``None`` when the course is whole. One reason, chosen in that
    #: order, because that is the order of what the teacher needs to
    #: know: a person's gap outranks a machine's.
    stuck_reason: Literal["needs_review", "failed_permanent", "translating"] | None = None
    #: How many (field, locale) pairs ``stuck_reason`` covers — the N in
    #: "N fragments are waiting for review".
    stuck_count: int = 0
    #: A translation job for this course is queued or running right now.
    #: ``False`` beside a non-empty ``stuck_reason`` is the state that
    #: used to be indistinguishable from "working on it": nothing will
    #: change until somebody acts.
    job_pending: bool = False


class ResyncProgressResponse(BaseModel):
    """What a progress resync did.

    ``enrollments_updated`` counts rows whose stored percentage actually
    changed, so a second press answering 0 is the confirmation that nothing
    is left to fix rather than a sign the button did nothing.
    """

    course_id: str
    enrollments_updated: int
