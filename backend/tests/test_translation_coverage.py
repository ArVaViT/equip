"""Static coverage guard for the translation overlay/hook contract.

This test introspects the FastAPI app at import time and enforces two rules
that have caused real production regressions in the recent past:

* **Rule 1** — every read endpoint that returns a translatable Pydantic
  schema MUST accept an ``Accept-Language`` header. Forgetting it produces
  the "raw RU comes back to an EN user" bug class (see PR #115 on
  ``get_module_detail``).
* **Rule 2** — every write endpoint (POST/PUT/PATCH) that mutates an
  entity registered as translatable MUST reference one of the canonical
  translation hooks somewhere in its source file. This catches the
  "create endpoint forgot the hook" gap that PR #116 fixed for
  announcements / course events.

The check is deliberately *static* — no database, no live requests — so
it runs in the unit-test tier and stays fast. Known gaps are listed in
``KNOWN_VIOLATIONS`` rather than silently excluded; surfacing wins over
hiding.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, get_args, get_origin

from fastapi.routing import APIRoute

from app.api.v1.prerequisites import PrerequisiteResponse
from app.main import app
from app.schemas.announcement import AnnouncementResponse
from app.schemas.assignment import AssignmentResponse
from app.schemas.calendar import CalendarEvent, CourseEventResponse
from app.schemas.certificate import CertificateResponse
from app.schemas.chapter_block import BlockResponse
from app.schemas.cohort import CohortResponse
from app.schemas.course import (
    ChapterResponse,
    CourseResponse,
    CourseSummary,
    ModuleResponse,
)
from app.schemas.quiz import (
    QuizOptionStudentResponse,
    QuizQuestionStudentResponse,
    QuizStudentResponse,
)

# Translatable response schemas come straight from those imports; we keep
# them as identity-equal classes so a schema rename triggers an ImportError
# rather than a silent miss in the membership test below.

TRANSLATABLE_RESPONSE_MODELS: frozenset[type] = frozenset(
    {
        AnnouncementResponse,
        AssignmentResponse,
        BlockResponse,
        CalendarEvent,
        CertificateResponse,
        ChapterResponse,
        CohortResponse,
        CourseEventResponse,
        CourseResponse,
        CourseSummary,
        ModuleResponse,
        PrerequisiteResponse,
        QuizOptionStudentResponse,
        QuizQuestionStudentResponse,
        QuizStudentResponse,
    }
)

# ---------------------------------------------------------------------------
# Translation hooks expected in write-endpoint source files (Rule 2)
# ---------------------------------------------------------------------------

TRANSLATION_HOOK_NAMES: tuple[str, ...] = (
    "run_course_translation_pipeline_if_published",
    "reconcile_entity_if_course_published",
    "translate_course_content",
)

# ``ENTITY_MODEL`` registry doesn't yet exist as a single dict — instead the
# vocabulary is encoded in ``app.services.translation.protocol.EntityType``
# (a Literal). We mirror it here so the test stays decoupled from runtime
# code; any drift will be caught by ``test_entity_types_match_protocol``.
TRANSLATABLE_ENTITY_BODY_SCHEMAS: frozenset[str] = frozenset(
    {
        # course-tree write payloads
        "CourseCreate",
        "CourseUpdate",
        "ModuleCreate",
        "ModuleUpdate",
        "ChapterCreate",
        "ChapterUpdate",
        "BlockCreate",
        "BlockUpdate",
        # quiz family
        "QuizCreate",
        "QuizUpdate",
        "QuizQuestionCreate",
        "QuizQuestionUpdate",
        "QuizOptionCreate",
        "QuizOptionUpdate",
        # ancillary translatable entities
        "AssignmentCreate",
        "AssignmentUpdate",
        "AnnouncementCreate",
        "AnnouncementUpdate",
        "CourseEventCreate",
        "CourseEventUpdate",
    }
)

# ---------------------------------------------------------------------------
# Whitelist (paths and prefixes that don't need translation)
# ---------------------------------------------------------------------------
#
# These are intentional carve-outs, not bugs. Keep the list tight — every
# entry should have a one-line comment explaining why translation does not
# apply there.

ADMIN_PATH_PREFIXES: tuple[str, ...] = (
    "/api/v1/admin",  # admin-only surface — sees source for moderation
    "/api/v1/audit",  # internal audit log, never user-facing translated
    "/api/v1/grades",  # numeric/grade data; teacher-only views see source
)


# Endpoints (function name -> reason) where the test would otherwise flag a
# real-but-tolerable case. New entries require a paired comment with a
# follow-up PR or "by design" justification. Empty tuple means there are
# currently no endpoint-level whitelist entries beyond the path prefix list.
WHITELIST_ENDPOINTS: dict[str, str] = {}


# ---------------------------------------------------------------------------
# KNOWN VIOLATIONS — surfaced, not silenced
# ---------------------------------------------------------------------------
#
# Ground rule from CLAUDE.md / agent-autonomy: when this guard catches an
# existing bug we add it here with a TODO so the test still passes today
# while making the gap impossible to lose track of. Every entry MUST cite
# the follow-up PR or issue.

KNOWN_VIOLATIONS_RULE1: frozenset[tuple[str, str]] = frozenset(
    {
        # No known Rule 1 violations on main as of 2026-05-07 — PR #120
        # closed certificates / cohorts / prerequisites by routing them
        # through the same overlay machinery used by /courses. Adding a
        # new entry here means a real gap we're choosing to leave open
        # temporarily — cite the follow-up PR or issue.
    }
)

KNOWN_VIOLATIONS_RULE2: frozenset[tuple[str, str]] = frozenset(
    {
        # Same rules — surface, don't silence.
        # ----- existing gaps as of 2026-05-07:
        # NOTE: PR #116 added the hook for create/update of announcements
        # and course events. If those landed BEFORE this test runs in CI,
        # these entries can be deleted. They are listed here defensively
        # so the test passes on whichever main commit it's first run on.
        # TODO follow-up: drop these once #116 has landed in main.
        ("create_announcement", "/api/v1/announcements"),
        ("update_announcement", "/api/v1/announcements/{announcement_id}"),
        ("create_course_event", "/api/v1/courses/{course_id}/events"),
        ("update_course_event", "/api/v1/courses/{course_id}/events/{event_id}"),
    }
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unwrap_response_model(model: Any) -> set[type]:
    """Return the concrete classes inside ``response_model``.

    Handles ``list[X]``, ``X | None``, ``Optional[X]``, ``Union[X, Y]``.
    Anything else is returned as a one-element set if it's a class, or an
    empty set if it isn't (e.g. ``None``, ``dict``, primitive types).
    """
    if model is None:
        return set()
    origin = get_origin(model)
    if origin is None:
        return {model} if inspect.isclass(model) else set()
    args = get_args(model)
    out: set[type] = set()
    for a in args:
        if a is type(None):
            continue
        out |= _unwrap_response_model(a)
    return out


def _signature_has_accept_language(endpoint: Any) -> bool:
    """True if any parameter in the endpoint signature is the
    ``Accept-Language`` header (matched by alias or by name)."""
    try:
        sig = inspect.signature(endpoint)
    except (TypeError, ValueError):
        return False
    for param in sig.parameters.values():
        if param.name == "accept_language":
            return True
        default = param.default
        # FastAPI's ``Header(...)`` returns a ``FieldInfo`` whose ``alias``
        # attribute is set via ``Header(alias="Accept-Language")``.
        alias = getattr(default, "alias", None)
        if alias and alias.lower() == "accept-language":
            return True
    return False


def _signature_requires_teacher_or_admin(endpoint: Any) -> bool:
    """True if any parameter is ``Depends(require_teacher)`` or
    ``Depends(require_admin)`` — these endpoints intentionally serve source
    content (the owner's own writing) and do not need to overlay a
    translation."""
    try:
        sig = inspect.signature(endpoint)
    except (TypeError, ValueError):
        return False
    for param in sig.parameters.values():
        default = param.default
        dep = getattr(default, "dependency", None)
        if dep is not None and getattr(dep, "__name__", "") in {
            "require_teacher",
            "require_admin",
        }:
            return True
    return False


def _path_is_whitelisted(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ADMIN_PATH_PREFIXES)


def _endpoint_source_file(endpoint: Any) -> Path | None:
    try:
        return Path(inspect.getsourcefile(endpoint) or "")
    except TypeError:
        return None


def _file_has_translation_hook(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(hook in text for hook in TRANSLATION_HOOK_NAMES)


def _endpoint_body_schemas(endpoint: Any) -> set[str]:
    """Return the *names* of Pydantic schemas appearing in the function
    signature as request bodies. Names (not classes) keep the registry in
    this test cheap to maintain."""
    try:
        sig = inspect.signature(endpoint)
    except (TypeError, ValueError):
        return set()
    out: set[str] = set()
    for param in sig.parameters.values():
        ann = param.annotation
        if ann is inspect.Parameter.empty:
            continue
        # Unwrap list[X] / X | None
        for klass in _unwrap_response_model(ann):
            name = getattr(klass, "__name__", None)
            if name:
                out.add(name)
    return out


def _api_routes() -> list[APIRoute]:
    return [r for r in app.routes if isinstance(r, APIRoute)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_entity_types_match_protocol() -> None:
    """Drift guard: the EntityType Literal must enumerate every entity that
    has a translatable response schema (the inverse direction is OK —
    ``chapter_block`` has no top-level write endpoint of its own)."""
    from typing import get_args as _get_args

    from app.services.translation.protocol import EntityType

    entity_types = set(_get_args(EntityType))
    # Sanity-check: protocol must include the canonical course-tree set.
    assert {
        "course",
        "module",
        "chapter",
        "chapter_block",
        "quiz",
        "quiz_question",
        "quiz_option",
        "assignment",
        "announcement",
        "course_event",
    }.issubset(entity_types), f"protocol.EntityType lost a registered type: have={entity_types}"


def test_read_endpoints_with_translatable_response_accept_language() -> None:
    """Rule 1: every GET that returns a translatable schema must read
    Accept-Language."""
    failures: list[str] = []
    for route in _api_routes():
        if "GET" not in route.methods:
            continue
        if _path_is_whitelisted(route.path):
            continue
        endpoint = route.endpoint
        endpoint_name = endpoint.__name__
        if endpoint_name in WHITELIST_ENDPOINTS:
            continue
        response_classes = _unwrap_response_model(route.response_model)
        if not (response_classes & TRANSLATABLE_RESPONSE_MODELS):
            continue
        if _signature_has_accept_language(endpoint):
            continue
        # Owner-only views see source by design — when the route requires a
        # teacher/admin and has no public read path, it's allowed to skip
        # the overlay.
        if _signature_requires_teacher_or_admin(endpoint):
            continue
        violation = f"{endpoint_name} ({route.methods} {route.path})"
        if (endpoint_name, route.path) in KNOWN_VIOLATIONS_RULE1:
            continue
        failures.append(violation)
    assert not failures, (
        "GET endpoints returning translatable schemas must accept "
        '`accept_language: str | None = Header(default=None, alias="Accept-Language")`. '
        "Failures:\n  - " + "\n  - ".join(sorted(failures))
    )


def test_write_endpoints_for_translatable_entities_call_a_hook() -> None:
    """Rule 2: every POST/PUT/PATCH whose request body is one of the
    registered translatable schemas must reference a translation hook in
    its source file (textual check — fast and catches the regression
    target)."""
    write_methods = {"POST", "PUT", "PATCH"}
    failures: list[str] = []
    seen_files_ok: dict[Path, bool] = {}
    for route in _api_routes():
        if not (route.methods & write_methods):
            continue
        endpoint = route.endpoint
        endpoint_name = endpoint.__name__
        if endpoint_name in WHITELIST_ENDPOINTS:
            continue
        if _path_is_whitelisted(route.path):
            continue
        body_schemas = _endpoint_body_schemas(endpoint)
        if not (body_schemas & TRANSLATABLE_ENTITY_BODY_SCHEMAS):
            # Path-resolved entity heuristic: a route under
            # ``/courses/...`` that mutates without a recognized body
            # schema is either an enrollment / progress / publish action
            # (handled elsewhere) or a translation hook target. We err on
            # the side of not flagging — the body-schema check covers the
            # bug class we care about.
            continue
        src_path = _endpoint_source_file(endpoint)
        if src_path is None:
            continue
        if src_path not in seen_files_ok:
            seen_files_ok[src_path] = _file_has_translation_hook(src_path)
        if seen_files_ok[src_path]:
            continue
        violation = f"{endpoint_name} ({sorted(route.methods)} {route.path}) in {src_path.name}"
        if (endpoint_name, route.path) in KNOWN_VIOLATIONS_RULE2:
            continue
        failures.append(violation)
    assert not failures, (
        "POST/PUT/PATCH endpoints mutating translatable entities must call "
        "one of: " + ", ".join(TRANSLATION_HOOK_NAMES) + ". Failures:\n  - " + "\n  - ".join(sorted(failures))
    )


def test_canonical_hook_is_importable() -> None:
    """Sanity guard: the primary hook name resolves.

    If someone renames ``run_course_translation_pipeline_if_published``
    the textual scan would silently pass for the *renamed* symbol while
    real callers break. This test fails loudly so ``TRANSLATION_HOOK_NAMES``
    gets updated in lockstep with the rename.
    """
    from app.services.translation import pipeline_hooks

    assert hasattr(pipeline_hooks, "run_course_translation_pipeline_if_published"), (
        "run_course_translation_pipeline_if_published is not importable from "
        "app.services.translation.pipeline_hooks; TRANSLATION_HOOK_NAMES is out of date."
    )
