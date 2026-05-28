"""Phase 2 dual-read comparator.

Compares the legacy read result (entity column + ``content_translations``
overlay) against what the new ``content_versions`` store would have
returned for the same ``(entity_type, entity_id, field, display_locale)``
lookup.

This module ONLY reports. It never changes the caller's return value.
Phase 2's whole job is to log every divergence so we can fix bugs (or
deliberately-acceptable differences) BEFORE Phase 4 switches reads to
``content_versions`` exclusively. Phase 4 then deletes the comparator
calls.

Edge cases we know about (from the dual-read audit). Each one is
represented by a distinct ``MismatchReason`` so the log filter can
slice by kind:

  * ``OK`` — both stores agree.
  * ``LEGACY_ONLY_NO_BACKFILL`` — no ``content_versions`` row for the
    entity at all. Expected on every pre-Phase-1 entity until Phase 3
    backfill runs. NOT a bug.
  * ``BOTH_FALL_BACK_TO_SOURCE`` — neither store has a translation
    for ``display_locale``; both correctly return the source text.
    Equality verified, no mismatch.
  * ``NEW_FAILED_STATUS`` — ``content_versions`` row exists but
    ``status`` is ``failed`` / ``failed_permanent``; the new resolver
    falls back to source. Compared against legacy fallback; mismatch
    only flagged if texts diverge.
  * ``TEXT_DIFFERS`` — both stores returned text but the texts differ
    after whitespace normalisation. The interesting case to triage.
  * ``LOCALE_DIVERGED`` — both stores returned text in the same
    display locale, but the underlying ``content_versions`` row was
    recorded under a different ``locale`` than the legacy path
    expected. This happens when per-field language detection
    classified a field differently from the course's declared
    ``source_locale``. NOT a bug — the new path is more correct —
    but worth surfacing so we can watch the rate.
  * ``NEW_ONLY`` — legacy returned the source base (no overlay),
    ``content_versions`` had a translation. Indicates the legacy
    overlay row was missed (or never written) but the new path
    captured it. Flag for investigation.
  * ``ENTITY_DELETED`` — the entity is soft-deleted on the legacy
    side but ``content_versions`` rows survive (no cascade wired
    yet). Phase 5 cleanup.

Hash / whitespace normalisation: comparison treats two strings as
equal if their ``compute_source_hash``-normalised form matches.
This catches trailing-newline drift and similar benign noise that
would otherwise dominate the mismatch counts.
"""

from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from app.models.content_version import ContentVersion
from app.services.translation.hash import _normalize as _normalize_whitespace

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Sampling rate for the dual-read comparator, 0.0 to 1.0. The comparator
# adds two single-row indexed SELECTs per call (active-at-display-locale
# + any-active-for-field) so even at rate=1.0 the overhead is small,
# but in prod we'll start at a low rate to confirm the wiring works
# without risk of log spam.
#
# Read once at import time — the env var changes a deploy. Tests that
# need to override use ``set_compare_sample_rate`` (a deliberate
# escape hatch; production code must not call it).
_DEFAULT_SAMPLE_RATE: float = float(os.environ.get("CONTENT_VERSIONS_COMPARE_RATE", "0.0") or "0.0")
_sample_rate: float = max(0.0, min(1.0, _DEFAULT_SAMPLE_RATE))


def set_compare_sample_rate(rate: float) -> None:
    """Test-only: override the dual-read comparator sampling rate.

    Production code reads ``CONTENT_VERSIONS_COMPARE_RATE`` from the
    environment at import time. This hook exists so per-test fixtures
    can flip the rate to 1.0 without monkey-patching the module
    constant directly.
    """
    global _sample_rate
    _sample_rate = max(0.0, min(1.0, rate))


def get_compare_sample_rate() -> float:
    return _sample_rate


class MismatchReason(StrEnum):
    OK = "ok"
    LEGACY_ONLY_NO_BACKFILL = "legacy_only_no_backfill"
    BOTH_FALL_BACK_TO_SOURCE = "both_fall_back_to_source"
    NEW_FAILED_STATUS = "new_failed_status"
    TEXT_DIFFERS = "text_differs"
    LOCALE_DIVERGED = "locale_diverged"
    NEW_ONLY = "new_only"
    ENTITY_DELETED = "entity_deleted"


# Reasons we treat as "interesting" — the caller's structured log + Datadog
# metric should fire for these. The remaining reasons are accounted-for
# benign states and we count them silently.
INTERESTING_REASONS: frozenset[MismatchReason] = frozenset(
    {
        MismatchReason.TEXT_DIFFERS,
        MismatchReason.LOCALE_DIVERGED,
        MismatchReason.NEW_ONLY,
        MismatchReason.ENTITY_DELETED,
    }
)


@dataclass(frozen=True, slots=True)
class MismatchReport:
    """One comparator outcome.

    Always constructed; the caller decides whether to log / emit a
    metric based on ``is_interesting``.
    """

    reason: MismatchReason
    entity_type: str
    entity_id: str
    field: str
    display_locale: str
    # Text the legacy resolve path returned (or None when it had nothing).
    legacy_text: str | None
    # Text the new resolve path would return (or None when it had nothing).
    new_text: str | None
    # The status of the active content_versions row at ``display_locale``,
    # or None when no row exists. Lets the log distinguish a missing row
    # from a failed one.
    new_status: str | None
    # The ACTUAL ``locale`` column of the active content_versions row for
    # this (entity, field) regardless of display_locale. None when no row.
    # Useful to spot per-field detection drift.
    new_recorded_locale: str | None

    @property
    def is_interesting(self) -> bool:
        return self.reason in INTERESTING_REASONS

    def to_log_fields(self) -> dict[str, str | None]:
        """Structured fields for the warning log."""
        return {
            "cv_compare_reason": self.reason.value,
            "cv_compare_entity_type": self.entity_type,
            "cv_compare_entity_id": self.entity_id,
            "cv_compare_field": self.field,
            "cv_compare_display_locale": self.display_locale,
            "cv_compare_new_status": self.new_status,
            "cv_compare_new_recorded_locale": self.new_recorded_locale,
            # Don't dump full text into structured fields — it can be
            # megabytes of HTML for chapter_block.content. Lengths are
            # enough to triage; pull the rows by id when debugging.
            "cv_compare_legacy_text_len": (str(len(self.legacy_text)) if self.legacy_text is not None else None),
            "cv_compare_new_text_len": (str(len(self.new_text)) if self.new_text is not None else None),
        }


def _entity_has_any_content_version(db: Session, *, entity_type: str, entity_id: str) -> bool:
    """Has the dual-write fired for this entity at all (any field, any locale)?

    Used to distinguish "Phase 3 backfill hasn't run for this entity yet"
    from "the write path is broken". Both look like missing rows but only
    the latter is a bug. A single existence query is enough to disambiguate.
    """
    return (
        db.query(ContentVersion.id)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
        )
        .first()
        is not None
    )


def _texts_match(a: str | None, b: str | None) -> bool:
    """Whitespace-normalised text equality.

    Mirrors ``compute_source_hash``'s ``\\s+`` collapse so a trailing
    newline or a re-flowed paragraph doesn't count as a mismatch.
    Both NULL ⇒ match. One NULL + one empty-string ⇒ also match,
    because the legacy path treats empty as no-value while the new
    path stores empty as the failure sentinel; treating them the same
    here means we don't flood logs with a known-irrelevant difference.
    """
    if not a and not b:
        return True
    if a is None or b is None:
        return False
    return _normalize_whitespace(a) == _normalize_whitespace(b)


def compare_resolved_text(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    source_locale: str,
    display_locale: str,
    base_source_text: str | None,
    legacy_text: str | None,
    entity_deleted: bool = False,
) -> MismatchReport:
    """Run the new-store resolve and compare against the legacy result.

    The caller has already executed the legacy resolution and passes the
    final string it would have returned to the user (``legacy_text``)
    along with the entity's source-column text (``base_source_text``).
    This function reads ``content_versions`` for the same key, applies
    the new-path resolution rules (active row at ``display_locale`` with
    ``status='ok'``; fall back to source otherwise), and returns a
    structured comparison.

    ``source_locale`` is the parent entity's declared source language
    (course.source_locale or equivalent). It lets the comparator
    distinguish "cv recorded the field at the expected source locale"
    (a benign confirmation) from "cv recorded the field at a locale
    that's neither display nor source" (per-field detection drift —
    interesting).

    No side effects — purely returns the report. The caller decides
    whether to log it, what sampling to apply, and which metric to
    emit. Phase 2 wiring lives outside this module.
    """
    active_row_for_display_locale = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.locale == display_locale,
            ContentVersion.superseded_by.is_(None),
        )
        .one_or_none()
    )

    # One extra single-row lookup: the active row for this (entity, field)
    # in ANY locale, used purely to surface "the new store recorded this
    # under a different locale than the legacy expected" as its own
    # mismatch class. Cheap, indexed by ix_content_versions_entity.
    any_active_for_field = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == "ok",
        )
        .first()
    )

    # Edge case: nothing in content_versions for this entity at all.
    # Almost certainly "Phase 3 backfill hasn't run yet" for legacy
    # entities. Don't flood logs.
    if active_row_for_display_locale is None and any_active_for_field is None:
        if not _entity_has_any_content_version(db, entity_type=entity_type, entity_id=entity_id):
            return MismatchReport(
                reason=MismatchReason.LEGACY_ONLY_NO_BACKFILL,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                display_locale=display_locale,
                legacy_text=legacy_text,
                new_text=None,
                new_status=None,
                new_recorded_locale=None,
            )

    new_text: str | None
    new_status: str | None
    # ``new_recorded_locale`` reports the locale of the row that
    # actually drove the new-store resolution. When the display-locale
    # row exists it's that one (and equals display_locale by
    # construction); when it doesn't, fall back to the first active
    # row for the field — the "what locale did cv actually file this
    # under?" signal.
    if active_row_for_display_locale is not None:
        new_recorded_locale: str | None = active_row_for_display_locale.locale
    else:
        new_recorded_locale = any_active_for_field.locale if any_active_for_field is not None else None

    if active_row_for_display_locale is None:
        # No content_versions row at display_locale — same fallback as
        # legacy (return source). Will be ``BOTH_FALL_BACK_TO_SOURCE``
        # or ``LOCALE_DIVERGED`` depending on whether the new store has
        # the field in some OTHER locale.
        new_text = base_source_text
        new_status = None
    elif active_row_for_display_locale.status == "ok":
        new_text = active_row_for_display_locale.text
        new_status = "ok"
    else:
        # status='failed' / 'failed_permanent' — new resolver falls
        # back to source, same as legacy.
        new_text = base_source_text
        new_status = active_row_for_display_locale.status

    # Soft-delete: legacy reads typically filter out deleted entities;
    # content_versions has no delete cascade yet. Flag as its own kind
    # so the cleanup PR in Phase 5 can target it.
    if entity_deleted and (active_row_for_display_locale is not None or any_active_for_field is not None):
        return MismatchReport(
            reason=MismatchReason.ENTITY_DELETED,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            display_locale=display_locale,
            legacy_text=legacy_text,
            new_text=new_text,
            new_status=new_status,
            new_recorded_locale=new_recorded_locale,
        )

    # Failed/failed-permanent path: both paths fell back to source.
    # Compare with whitespace-normalisation; ``status`` reported back
    # so the metric can sort failures out of the "real" mismatches.
    if active_row_for_display_locale is not None and active_row_for_display_locale.status != "ok":
        if _texts_match(legacy_text, new_text):
            return MismatchReport(
                reason=MismatchReason.NEW_FAILED_STATUS,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                display_locale=display_locale,
                legacy_text=legacy_text,
                new_text=new_text,
                new_status=new_status,
                new_recorded_locale=new_recorded_locale,
            )
        return MismatchReport(
            reason=MismatchReason.TEXT_DIFFERS,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            display_locale=display_locale,
            legacy_text=legacy_text,
            new_text=new_text,
            new_status=new_status,
            new_recorded_locale=new_recorded_locale,
        )

    if active_row_for_display_locale is None:
        # No row at display_locale → both paths fall back to source.
        # Distinguish two sub-cases by what cv has for the field in
        # OTHER locales:
        #   * any_active_for_field is None: cv has nothing → already
        #     handled above as LEGACY_ONLY_NO_BACKFILL (the field
        #     hasn't been dual-written yet for ANY locale).
        #   * any_active_for_field at source_locale: cv recorded the
        #     field at the EXPECTED source locale. Benign.
        #   * any_active_for_field at a third locale: per-field
        #     detection put the field somewhere unexpected. Surface
        #     it so we can review whether the detection was right.
        if (
            any_active_for_field is not None
            and any_active_for_field.locale != source_locale
            and any_active_for_field.locale != display_locale
        ):
            # Recorded under neither display nor source. Texts may
            # still match if both fell back to source — the divergence
            # signal is the recorded locale itself.
            if _texts_match(legacy_text, new_text):
                return MismatchReport(
                    reason=MismatchReason.LOCALE_DIVERGED,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field=field,
                    display_locale=display_locale,
                    legacy_text=legacy_text,
                    new_text=new_text,
                    new_status=None,
                    new_recorded_locale=new_recorded_locale,
                )
            return MismatchReport(
                reason=MismatchReason.TEXT_DIFFERS,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                display_locale=display_locale,
                legacy_text=legacy_text,
                new_text=new_text,
                new_status=None,
                new_recorded_locale=new_recorded_locale,
            )
        # cv has nothing OR has the field at source/display locale only.
        # Either way both paths converged on the source text.
        if _texts_match(legacy_text, new_text):
            return MismatchReport(
                reason=MismatchReason.BOTH_FALL_BACK_TO_SOURCE,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                display_locale=display_locale,
                legacy_text=legacy_text,
                new_text=new_text,
                new_status=None,
                new_recorded_locale=new_recorded_locale,
            )
        return MismatchReport(
            reason=MismatchReason.TEXT_DIFFERS,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            display_locale=display_locale,
            legacy_text=legacy_text,
            new_text=new_text,
            new_status=None,
            new_recorded_locale=new_recorded_locale,
        )

    # Active ok row exists at display_locale.
    if legacy_text == base_source_text or legacy_text is None:
        # Legacy fell back to source (or returned None); new store has
        # a translation. Flag — the legacy overlay was missed.
        return MismatchReport(
            reason=MismatchReason.NEW_ONLY,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            display_locale=display_locale,
            legacy_text=legacy_text,
            new_text=new_text,
            new_status="ok",
            new_recorded_locale=new_recorded_locale,
        )
    if _texts_match(legacy_text, new_text):
        return MismatchReport(
            reason=MismatchReason.OK,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            display_locale=display_locale,
            legacy_text=legacy_text,
            new_text=new_text,
            new_status="ok",
            new_recorded_locale=new_recorded_locale,
        )
    return MismatchReport(
        reason=MismatchReason.TEXT_DIFFERS,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        display_locale=display_locale,
        legacy_text=legacy_text,
        new_text=new_text,
        new_status="ok",
        new_recorded_locale=new_recorded_locale,
    )


def maybe_compare_and_log(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    source_locale: str,
    display_locale: str,
    base_source_text: str | None,
    legacy_text: str | None,
    entity_deleted: bool = False,
) -> None:
    """Sample-gated wrapper around ``compare_resolved_text``.

    Production read sites call THIS instead of the bare comparator.
    Three responsibilities, in order:

    1. Sampling — skip cleanly when the env-controlled sample rate
       says this call shouldn't compare. Default rate is 0.0, so the
       function is a no-op until ops flip the dial. Compared rows pay
       two indexed SELECTs, so even at 1.0 the overhead is small, but
       starting low gives us a safe rollout.
    2. Comparator — call the pure ``compare_resolved_text`` with the
       same args.
    3. Logging — emit a structured ``warning`` for INTERESTING reasons.
       Benign reasons (OK / no-backfill / fallback agreement / failed
       status / locale at source) are silently dropped so we don't
       drown the log feed during the unbackfilled-prod phase.

    Wraps every call in a ``try / except`` because Phase 2's whole
    contract is "comparison MUST NOT affect the user's response".
    A bug in the comparator (or a flaky DB read) should never bubble
    up to the read endpoint that called us.
    """
    if _sample_rate <= 0.0:
        return
    if _sample_rate < 1.0 and random.random() >= _sample_rate:
        return
    try:
        report = compare_resolved_text(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            source_locale=source_locale,
            display_locale=display_locale,
            base_source_text=base_source_text,
            legacy_text=legacy_text,
            entity_deleted=entity_deleted,
        )
    except Exception:
        # The comparator does only reads, but if a DB hiccup throws we
        # silently swallow and move on. Phase 2 is observation, not a
        # correctness path.
        logger.exception("content_versions dual-read comparator raised; swallowing")
        return
    if report.is_interesting:
        logger.warning(
            "content_versions dual-read mismatch: %s",
            report.reason.value,
            extra=report.to_log_fields(),
        )
