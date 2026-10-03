"""Edits to a live course, held until every language has them.

Public surface, in the order the lifecycle uses it:

* ``course_of_entity`` / ``edit_should_be_staged`` — is this entity part
  of a course students are reading right now?
* ``stage_human_edit`` — record the teacher's new text without serving
  it, and drop any translations of the text it replaces.
* ``staged_field_specs`` — what the pipeline still has to translate.
* ``promote_ready_fields`` — move every whole field into
  ``content_versions`` in one transaction, so all four languages change
  together.
* ``clear_staged_entity`` — an entity was deleted; its unreleased edit
  goes with it.
* ``awaiting_first_release`` / ``chapter_awaits_first_release`` — new
  content whose text has never been released: readers are not shown it
  and are not counted against it (2026-10-03).
"""

from app.services.staged_edits.promote import (
    PromotionReport,
    promote_ready_fields,
    promote_staged_entity_unconditionally,
)
from app.services.staged_edits.read import (
    StagedFieldStatus,
    author_text,
    author_texts_bulk,
    author_texts_in_locale,
    staged_field_specs,
    staged_status_for_course,
    staged_texts_for_entity,
)
from app.services.staged_edits.visibility import (
    awaiting_first_release,
    awaiting_first_release_sql,
    chapter_awaits_first_release,
    chapter_is_held,
)
from app.services.staged_edits.write import (
    clear_staged_entity,
    clear_staged_field,
    course_of_entity,
    edit_should_be_staged,
    stage_human_edit,
)

__all__ = [
    "PromotionReport",
    "StagedFieldStatus",
    "author_text",
    "author_texts_bulk",
    "author_texts_in_locale",
    "awaiting_first_release",
    "awaiting_first_release_sql",
    "chapter_awaits_first_release",
    "chapter_is_held",
    "clear_staged_entity",
    "clear_staged_field",
    "course_of_entity",
    "edit_should_be_staged",
    "promote_ready_fields",
    "promote_staged_entity_unconditionally",
    "stage_human_edit",
    "staged_field_specs",
    "staged_status_for_course",
    "staged_texts_for_entity",
]
