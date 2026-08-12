from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GradeUpsert(BaseModel):
    """A hand-set grade (D7).

    Exactly one of ``override_code`` / ``override_score`` — a symbol from the
    course's scheme, or a percentage for ``percent`` courses. The pairing is
    checked against the course itself in the route, because which symbols are
    legal depends on the scheme: «5» is a grade in a five-point course and
    nonsense in a letter one.

    Clearing a grade is a DELETE on the same route, not an empty value here.
    The old shape used "field omitted means leave it alone", which made an
    override impossible to remove: once a teacher had set an F, no request
    could take it back.
    """

    override_code: str | None = Field(None, max_length=8)
    override_score: Decimal | None = Field(None, ge=0, le=100)
    reason: str | None = Field(None, max_length=2000)
    comment: str | None = Field(None, max_length=5000)


class StudentGradeResponse(BaseModel):
    """What a student may see of their own hand-set grade.

    Deliberately without ``reason``. That field is the teacher's note to the
    institution — "passed at the pastor's request", "corrected after the appeal"
    — and D7 scopes it to directors. ``comment`` is the note written *to* the
    student and is rendered to them by design (D10.3); the two are different
    audiences and must not share a schema.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    course_id: str
    cohort_id: UUID | None = None
    override_code: str | None = None
    override_score: Decimal | None = None
    computed_score: Decimal | None = None
    comment: str | None = None
    graded_at: datetime
    updated_at: datetime | None = None


class GradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    course_id: str
    cohort_id: UUID | None = None
    override_code: str | None = None
    override_score: Decimal | None = None
    #: What the calculator said when the override was set — kept so both
    #: numbers can be shown together instead of the hand-set one alone.
    computed_score: Decimal | None = None
    reason: str | None = None
    comment: str | None = None
    graded_by: UUID | None = None
    graded_at: datetime
    updated_at: datetime | None = None


class GradingConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quiz_weight: int
    assignment_weight: int
    participation_weight: int


class GradingConfigUpdate(BaseModel):
    """Course weights on the write path — two categories, never three.

    "Participation" was retired as a weighted category (D5). The field is still
    accepted because browsers that loaded the SPA before the change keep PUTing
    the old 30/50/20 shape, and answering a stale tab with a 422 would strand a
    teacher mid-edit with an error they cannot act on. Instead the server folds
    the participation share into the two real categories and stores 0, applying
    the same two rules as the migration so a stale tab and a fresh one converge:

    * the untouched platform default 30/50/20 becomes the new default 40/60 —
      not the 38/62 proportional arithmetic would give. Nobody chose 30/50/20,
      and carrying that non-decision forward would leave a school with two
      different splits and a number no teacher can reproduce on paper;
    * weights a teacher actually set keep their ratio.
    """

    quiz_weight: int = Field(..., ge=0, le=100)
    assignment_weight: int = Field(..., ge=0, le=100)
    participation_weight: int = Field(0, ge=0, le=100)

    @model_validator(mode="after")
    def normalize_and_validate(self):
        total = self.quiz_weight + self.assignment_weight + self.participation_weight
        if total != 100:
            raise ValueError(f"Weights must sum to 100, got {total}")

        if self.participation_weight:
            base = self.quiz_weight + self.assignment_weight
            if (self.quiz_weight, self.assignment_weight, self.participation_weight) == (30, 50, 20):
                # The old platform default — a non-decision, not a choice.
                self.quiz_weight, self.assignment_weight = 40, 60
            elif base == 0:
                # Nothing to fold into; inventing a ratio would be arbitrary.
                self.quiz_weight, self.assignment_weight = 40, 60
            else:
                # Ties round away from zero, matching Postgres `round()` in the
                # migration rather than Python's round-half-to-even.
                self.quiz_weight = int(
                    (Decimal(self.quiz_weight * 100) / Decimal(base)).quantize(Decimal("1"), ROUND_HALF_UP)
                )
                self.assignment_weight = 100 - self.quiz_weight
            self.participation_weight = 0

        return self


class GradingSchemeUpdate(BaseModel):
    """Scheme and pass line, written together or not at all (D8.1).

    They are a pair: a five-point course whose pass line sits above 75 has an
    unreachable «3» band, and the only way to catch that is to validate both
    at once. A scheme-only write could otherwise leave a course in a state no
    student can satisfy.
    """

    grading_scheme: Literal["pass_fail", "percent", "five_point", "letter"]
    pass_threshold: Decimal = Field(..., ge=0, le=100)
    #: Optional note recorded in the audit entry — why the school changed how
    #: this course is graded. Changing a scheme mid-course is exactly the kind
    #: of decision a director will be asked about later.
    reason: str | None = Field(None, max_length=2000)


class GradingSchemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    grading_scheme: str
    pass_threshold: Decimal
    #: The bands this course's grades are read against, resolved from the
    #: institution's settings. Exported so the client renders from the
    #: backend's answer instead of a copy of the scale.
    bands: list[tuple[Decimal, str]] = []


class ExemptionCreate(BaseModel):
    """Excuse a student from one piece of work (D6)."""

    item_type: Literal["quiz", "assignment"]
    item_id: UUID
    #: Optional, director-visible. Waiving work is a decision someone will be
    #: asked about, especially when it is the last thing between a student and
    #: a certificate.
    reason: str | None = Field(None, max_length=2000)


class ExemptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    course_id: str
    item_type: str
    item_id: UUID
    reason: str | None = None
    created_by: UUID | None = None
    created_at: datetime | None = None


class GradeBreakdown(BaseModel):
    """One student's grade, with the arithmetic shown rather than implied.

    The *effective* weights are what the score is actually computed from, and
    they are what every surface must display (D4). A course with quizzes and no
    assignments used to be capped: the empty assignment category kept its
    weight and contributed zero, so the largest production course — 4 quizzes,
    0 assignments, 13 students — could not exceed 60% no matter what a student
    did. An empty category now drops out and its weight is redistributed at
    calculation time, so a teacher adding their first assignment mid-course
    just works.

    ``result_state`` distinguishes an ordinary graded course from one with
    nothing gradable in it at all, where there is no number to compute and the
    honest answer is «зачёт (по завершению)» rather than a silent zero.
    """

    quiz_avg: float
    quiz_weighted: float
    assignment_avg: float
    assignment_weighted: float
    participation_pct: float
    participation_weighted: float
    final_score: float
    letter_grade: str
    #: «Текущая оценка» — the same marks over only the work that has been
    #: marked. «Итоговая» (``final_score``) counts everything not yet handed in
    #: as a zero.
    #:
    #: Both, under the same names, for both roles (D10). Giving the student one
    #: and the teacher the other is how you get an unexplainable 85%-vs-40% gap
    #: in week two, with each side certain their own number is the grade. The
    #: pair is shown as a pair; when they are equal there is one number and
    #: nothing to explain.
    current_score: float = 0.0
    current_letter_grade: str = ""
    #: True when the two differ, so every surface can render the one-line
    #: reason («итоговая считает несданные работы как 0») in the same words. The
    #: student meets «итоговая» the day it diverges, never as a surprise at
    #: certificate time.
    scores_differ: bool = False

    #: Weights after empty categories drop out. Equal to the configured
    #: weights when both categories have items.
    effective_quiz_weight: int = 0
    effective_assignment_weight: int = 0
    #: Whether the course *contains* items of each kind. Distinct from the
    #: weights above: a course can have assignments that carry no weight yet
    #: because none are marked. The UI needs both to word its explanation
    #: honestly — telling a teacher to "mark the first assignment" when the
    #: course has no assignments at all sends them looking for something that
    #: does not exist.
    has_quiz_items: bool = False
    has_assignment_items: bool = False
    #: Whether **this student** has at least one marked piece of work in each
    #: category. This is what separates "0% because they got everything wrong"
    #: from "0% because nobody has read theirs" — arithmetically identical,
    #: opposite meanings, and only one of them belongs on a screen as a number.
    #:
    #: Deliberately per-student, unlike the course-wide liveness that drives
    #: weight redistribution. Conflating the two puts a 0 on the row of every
    #: unmarked student in a class where anyone has been marked, which is the
    #: exact reading the flag exists to prevent.
    student_has_quiz_marks: bool = False
    student_has_assignment_marks: bool = False
    #: Whether the course has chapters *meant* to be graded. A chapter typed
    #: "quiz" exists the moment a teacher creates it, but the quiz itself is
    #: only saved once it has questions — so a course under construction has
    #: gradable chapters and no gradable items. Without this the platform
    #: cheerfully announces "this course has no quizzes, that is not an error"
    #: while a chapter named «Тест 1» sits in it.
    has_gradable_chapters: bool = False
    #: True when the effective weights differ from what the teacher configured,
    #: so the UI can explain why ("this course has no assignments, so their
    #: weight moved to quizzes") instead of showing a number that contradicts
    #: the settings page.
    weights_redistributed: bool = False
    #: ``graded`` — an ordinary weighted result.
    #: ``completion_pass`` — the course contains no quizzes and no assignments
    #: at all, so there is nothing to compute; the result is completion-based.
    #: This is a fact about the *course*, not about the student: it does not by
    #: itself mean this student passed — that still depends on progress.
    #: ``not_graded_yet`` — the course has gradable items, but nothing has been
    #: graded in it yet (start of term, or a fresh cohort). Distinct from
    #: ``completion_pass`` on purpose: telling a teacher "this course has no
    #: quizzes" while four quizzes sit in it is a lie, and showing 0%/F to a
    #: class that has not been marked yet is a different lie.
    #: ``zero_weighted`` — work *has* been graded, but only in a category the
    #: teacher set to 0%. Quizzes as practice self-checks with the essay
    #: carrying the grade is the ordinary case. Separate from
    #: ``not_graded_yet`` because "nothing has been graded yet" would be false
    #: and the advice that follows it ("percentages appear once someone takes a
    #: quiz") would promise something that has already happened and will never
    #: help. The averages stay populated here — they are real, they just carry
    #: no weight.
    #: ``not_assessed`` — «не аттестован». Every gradable item this student owed
    #: was excused (D6), so there is no denominator left and no honest number.
    #: It must not collapse into ``completion_pass``: excusing an item also
    #: completes its chapter, so a student excused from everything sits at
    #: progress 100, and "passed by completion" would hand them a certificate
    #: for work nobody ever assessed. A teacher decides this one by hand.
    result_state: Literal["graded", "completion_pass", "not_graded_yet", "zero_weighted", "not_assessed"] = "graded"


class StudentCalculatedGrade(BaseModel):
    student_id: str
    student_name: str | None
    student_email: str
    breakdown: GradeBreakdown
    manual_grade: str | None = None


class GradeSummaryResponse(BaseModel):
    course_id: str
    config: GradingConfigResponse
    students: list[StudentCalculatedGrade]
    #: ``None`` when the course has nothing graded to average — a
    #: completion-only course, or one where marking has not started. Zero would
    #: be a lie the size of the whole class.
    class_average: float | None = None
    #: How this course is graded, and the bands its symbols are read against.
    #: Sent so the client renders from the school's own scale instead of the
    #: copy of the letter scale it used to keep — a copy that silently sorted «5» equal to
    #: «2» and greyed out every grade the moment a school picked another
    #: scheme, while the numbers beside them stayed correct.
    grading_scheme: str = "letter"
    bands: list[tuple[Decimal, str]] = []


# ---------------------------------------------------------------------------
# What a student sees of their own grade (D10)
# ---------------------------------------------------------------------------

#: The four states a piece of work can be in, from the student's side.
#:
#: ``pending_review`` is the one that did not exist before and matters most. An
#: essay sits at 0 out of 10 with ``passed = false`` from the moment it is
#: submitted until a teacher reads it, and the student had no way to tell that
#: apart from a genuine zero — they were shown a failure for work nobody had
#: looked at yet. The teacher's gradebook stopped doing that this week; this is
#: the same fix on the side of the person it frightens.
#: ``returned`` is the fifth, and it is not a variant of ``pending_review``:
#: pending work waits on the **teacher**, returned work waits on the
#: **student**. They look identical in a list and mean opposite things about
#: whose move it is — and a returned essay carries a grade, so without its own
#: status it rendered as «проверено» while the course result said «незачёт»,
#: with nothing on screen joining the two.
ItemStatus = Literal["graded", "pending_review", "returned", "not_submitted", "excused"]


class MyGradeItem(BaseModel):
    """One piece of work, as its owner sees it.

    Identified by the item, not the chapter: nothing stops a chapter holding
    two quizzes, and keying a list by chapter collapses them into one row.
    """

    item_id: str
    chapter_id: str
    title: str
    kind: Literal["quiz", "assignment"]
    status: ItemStatus
    #: Percentage, present only for ``graded``. A number on a `pending_review`
    #: row would be the running total, which is exactly the thing being hidden.
    score: float | None = None


class CertificateBlocker(BaseModel):
    """One reason a certificate is not available yet.

    A code and numbers, never a sentence. The words live in the frontend
    catalogues so that adding a language is a translation change and not a
    backend release, and so the student's screen and the teacher's card cannot
    word the same obstacle differently.
    """

    code: str
    #: Numbers the sentence needs: ``{"count": 2}``, ``{"final_score": 64.0,
    #: "pass_threshold": 70.0}``.
    #: ``bool`` leads the union deliberately: Python bools are ints, and a
    #: union that meets ``int`` first turns ``provisional: true`` into ``1``.
    params: dict[str, bool | int | float | str] = {}
    #: The chapters to link to. A refusal that names a problem without saying
    #: where it is sends the student to the teacher instead of to the work.
    chapter_ids: list[str] = []


class MyCourseGrade(BaseModel):
    """A student's own standing in one course.

    Deliberately absent, and absent by design rather than by omission (D10.4):
    the class average, any other student's name, any rank or percentile. A
    grade is between a student, their teacher and the school. Nothing here is
    comparative, and there is no field a future caller could fill with a peer's
    data without changing this schema on purpose.

    ``comment`` is the teacher's note **to the student** and is rendered; the
    ``reason`` on the same database row is the note *about* them, written for
    the institution, and never appears in a student-facing schema (D7).
    """

    course_id: str
    grading_scheme: str
    pass_threshold: Decimal
    progress: int

    #: «Текущая» and «итоговая» — the pair, always together (D10.1). ``None``
    #: when there is no honest number: nothing marked yet, nothing gradable in
    #: the course, or every item excused.
    current_score: float | None = None
    current_symbol: str | None = None
    final_score: float | None = None
    final_symbol: str | None = None
    scores_differ: bool = False
    #: Why there is no number, when there is none — the same vocabulary the
    #: teacher's screens use, so the two sides describe one situation.
    result_state: str = "graded"
    #: True when the course is graded on a scheme whose rule is completion-based
    #: rather than arithmetic (``pass_fail``, D2). The weighted percentage is
    #: then not the result and must not be shown as one, so the scores are
    #: withheld rather than dressed up.
    scores_withheld: bool = False
    #: For a completion-graded course, the verdict itself: «зачёт», «незачёт»
    #: or «не аттестован». There is no percentage behind it by design (D2) —
    #: the rule is whether every required piece of work was accepted.
    zachet: Literal["zachet", "nezachet", "not_attested"] | None = None

    #: The hand-set grade, when a teacher set one. It IS the official grade
    #: (D7), so it is what the student is told.
    official_grade: str | None = None
    comment: str | None = None

    #: Why the certificate is not available yet — specifics, in reading order,
    #: with deep links (D9). Empty means nothing stands in the way.
    #:
    #: This ships **before** the gate that will enforce it (Принцип 2): a
    #: refusal a student cannot act on becomes a message to the teacher, and a
    #: teacher who gets that message five times a week starts approving
    #: certificates to make it stop.
    certificate_blockers: list[CertificateBlocker] = []

    items: list[MyGradeItem] = []


# ---------------------------------------------------------------------------
# Ведомость (D11 / M5)
# ---------------------------------------------------------------------------


class SheetRowResponse(BaseModel):
    """One student's line on a closed sheet."""

    model_config = ConfigDict(from_attributes=True)

    student_id: UUID
    student_name: str | None = None
    result_state: Literal["pass", "fail", "completion_pass", "not_attested"]
    official_code: str | None = None
    official_score: Decimal | None = None
    #: The director-visible glyph: set by hand, not computed. Someone about to
    #: sign should see that at a glance rather than have to ask.
    is_override: bool = False


class GradeSheetResponse(BaseModel):
    """A closed ведомость, as the printable renders it.

    Everything here is read from the snapshot, never recomputed. A document
    whose numbers move after signature is not a document.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: str
    #: The course title as it read at closing, in this document's language.
    #: Courses get retitled; a signed heading does not.
    course_title: str | None = None
    #: The language this document was closed in. The interface locale belongs
    #: to the reader; a signed page keeps its own.
    locale: str = "en"
    cohort_id: UUID | None = None
    #: The поток's name as it stood at closing — cohort names are editable and
    #: a signed heading is not.
    cohort_name: str | None = None
    cohort_start: datetime | None = None
    cohort_end: datetime | None = None
    #: The institutional letterhead, frozen with everything else. A school
    #: renames itself and a teacher leaves; a filed document does neither.
    school_name: str | None = None
    school_city: str | None = None
    teacher_name: str | None = None
    academic_hours: int | None = None
    grading_scheme: str
    pass_threshold: Decimal | None = None
    finalized_at: datetime
    finalized_by: UUID | None = None
    reopened_at: datetime | None = None
    reopen_reason: str | None = None
    #: Set when this sheet replaced a reopened one — the «была переоткрыта»
    #: mark, on the document people will actually print.
    corrects_sheet_id: UUID | None = None
    correction_reason: str | None = None
    rows: list[SheetRowResponse] = []


class SheetReopenRequest(BaseModel):
    """Reopening is deliberate and on the record, so the reason is required."""

    reason: str = Field(..., min_length=1, max_length=2000)


class RetakeRequestResponse(BaseModel):
    """The answer to «запросить пересдачу» (D12).

    Idempotent by design: a student who taps twice, or who asks again the same
    afternoon, gets the same answer rather than a second item in the teacher's
    queue. The recovery path has to be safe to use when you are anxious about
    failing, which is the state everybody who uses it is in.
    """

    status: Literal["requested", "already_requested"]


class GradeHistoryEntry(BaseModel):
    """One thing that happened to this student's grade, and who did it.

    A hand-set grade is the one number on the page nobody can reconstruct from
    the work. Six months later, at the point where somebody signs a ведомость,
    "why is this a B when the system says 64" has to have an answer that is not
    a person's memory. The audit rows already existed; nothing read them.
    """

    id: UUID
    action: str
    at: datetime
    actor_id: UUID | None = None
    #: The name at the time of reading, not at the time of the act — a renamed
    #: teacher is the same person, and this is a working screen, not a document.
    actor_name: str | None = None

    #: Override entries.
    override_code: str | None = None
    override_score: Decimal | None = None
    #: What the calculator said when the grade was set by hand. "Teacher set B"
    #: says little; "teacher set B where the system had computed 64%" is the
    #: sentence a director actually needs.
    computed_score: Decimal | None = None
    #: The note written for the institution (D7). Teacher-facing only — this
    #: schema never reaches a student, and `MyCourseGrade` has no such field.
    reason: str | None = None

    #: Exemption entries.
    item_type: str | None = None
    item_id: str | None = None

    #: Retake-request entries: what was blocking them when they asked.
    blockers: list[str] = []


class RetakeRequest(BaseModel):
    """One open «запросить пересдачу», as the teacher's course pages see it."""

    student_id: UUID
    requested_at: datetime | None = None
    #: What was blocking them when they asked, so the teacher arrives already
    #: knowing which of their four powers this calls for rather than opening
    #: four screens to find out.
    blockers: list[str] = []


class PendingGradingSummary(BaseModel):
    """What a teacher owes, counted once.

    Only work waiting on **them**: an unread open answer, a submitted
    assignment with no mark. Work the student owes — never handed in, or handed
    back for revision — is deliberately absent. A number a teacher cannot act
    on is a number they stop reading.
    """

    total: int = 0
    by_course: dict[str, int] = {}
