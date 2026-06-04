"""Course cover ``image_url`` must reject dangerous URL schemes on input.

The value is stored and later rendered into an ``<img src>`` / CSS
background. React escapes attributes, but keeping ``javascript:`` /
``data:`` / bare ``http://`` out of the DB is defence-in-depth for any
future non-React consumer. The validator allows real shapes: a
fully-qualified ``https://`` URL (Supabase storage) or a same-origin
``/img/`` proxy path.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas._media_url import validate_safe_media_url
from app.schemas.course import CourseCreate, CourseUpdate


@pytest.mark.parametrize(
    "value",
    [
        "https://abc.supabase.co/storage/v1/object/public/covers/c.jpg",
        "/img/covers/c.jpg",
        None,
        "",
        "   ",
    ],
)
def test_validator_accepts_safe_values(value: str | None) -> None:
    # No exception; empty/whitespace normalise to None.
    result = validate_safe_media_url(value)
    if value and value.strip():
        assert result == value.strip()
    else:
        assert result is None


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "http://insecure.example.com/x.jpg",  # bare http rejected
        "//evil.example.com/x.jpg",  # protocol-relative is NOT same-origin
    ],
)
def test_validator_rejects_dangerous_or_insecure_values(value: str) -> None:
    with pytest.raises(ValueError):
        validate_safe_media_url(value)


def test_course_create_rejects_javascript_url() -> None:
    with pytest.raises(ValidationError):
        CourseCreate(title="X", image_url="javascript:alert(1)")


def test_course_update_rejects_javascript_url() -> None:
    with pytest.raises(ValidationError):
        CourseUpdate(image_url="javascript:alert(1)")


def test_course_create_accepts_https_cover() -> None:
    c = CourseCreate(title="X", image_url="https://abc.supabase.co/covers/c.jpg")
    assert c.image_url == "https://abc.supabase.co/covers/c.jpg"
