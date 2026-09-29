"""«Neues Ereignis: Экзамен „…“» — the frame re-rendered in the reader's new
language, the event's kind frozen in the one they read when the row was
written (2026-09-29). A kind is a catalog key now, translated when shown."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.notification_service import (
    I18N_KEY,
    notification_text,
    render_notification,
    translatable,
)


def _row(**params: object) -> SimpleNamespace:
    return SimpleNamespace(
        id="n-1",
        title="stored",
        message="stored",
        meta={I18N_KEY: notification_text("notif.new_event", **params)},
    )


def test_the_kind_is_in_the_readers_current_language() -> None:
    row = _row(kind=translatable("event_type.exam"), title="Final", course="Acts")
    _, en = render_notification(row, "en")
    _, ru = render_notification(row, "ru")
    assert "Exam" in en or "exam" in en
    assert "Экзамен" in ru or "экзамен" in ru
    assert en != ru


def test_plain_parameters_are_left_as_they_are() -> None:
    row = _row(kind="Exam", title="Final", course="Acts")
    _, de = render_notification(row, "de")
    assert "Exam" in de and "Final" in de
