"""Unit tests for ``app.core.course_cover_upload``.

The course-cover upload helper bridges the FastAPI route to Supabase
Storage's REST API. It is server-only (uses the service-role key, which
bypasses storage RLS) and must keep the object layout + public URL shape
identical to what the frontend already generates via ``getPublicUrl``.

Tests pin three things:

1. ``public_img_path_for_course_cover`` returns the exact same URL shape
   the frontend builds.
2. ``upload_course_cover_bytes`` posts to the correct Storage REST
   endpoint with the right headers (service-role bearer, ``x-upsert``,
   content-type for the requested image extension).
3. The error path raises ``RuntimeError`` for non-2xx responses so the
   caller doesn't silently return a "valid" URL for a failed upload.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core import course_cover_upload as ccu


class TestPublicImgPath:
    def test_default_extension_is_png(self) -> None:
        assert ccu.public_img_path_for_course_cover("abc-123", "") == "/img/course-assets/abc-123/cover.png"

    def test_lowercases_extension(self) -> None:
        assert ccu.public_img_path_for_course_cover("abc-123", "JPG") == "/img/course-assets/abc-123/cover.jpg"

    def test_strips_leading_dot(self) -> None:
        assert ccu.public_img_path_for_course_cover("abc-123", ".webp") == "/img/course-assets/abc-123/cover.webp"

    def test_unknown_extension_passes_through(self) -> None:
        """Path builder is permissive — extension normalisation lives in
        the upload function. This keeps the URL-shape helper a pure
        string transform with no side-effects or surprises.
        """
        assert ccu.public_img_path_for_course_cover("abc-123", "tiff") == "/img/course-assets/abc-123/cover.tiff"


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class _FakeClient:
    """Drop-in for ``httpx.Client`` used in the upload tests. Captures
    the args the SUT passes so we can assert on URL / headers / body.
    """

    def __init__(self, *, response: _FakeResponse) -> None:
        self._response = response
        self.posted_url: str | None = None
        self.posted_content: bytes | None = None
        self.posted_headers: dict[str, str] | None = None

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def post(self, url: str, *, content: bytes, headers: dict[str, str]) -> _FakeResponse:
        self.posted_url = url
        self.posted_content = content
        self.posted_headers = headers
        return self._response


def _install_fake_client(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse) -> _FakeClient:
    fake = _FakeClient(response=response)

    def factory(*_args: Any, **_kwargs: Any) -> _FakeClient:
        return fake

    monkeypatch.setattr(ccu.httpx, "Client", factory)
    return fake


class TestUploadCourseCoverBytes:
    SUPABASE_URL = "https://proj.supabase.co"
    SERVICE_KEY = "service-role-secret"
    COURSE_ID = "course-xyz"
    PAYLOAD = b"\x89PNG\r\n\x1a\nfake-bytes"

    def test_success_returns_public_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _install_fake_client(monkeypatch, _FakeResponse(200))
        result = ccu.upload_course_cover_bytes(
            self.SUPABASE_URL,
            self.SERVICE_KEY,
            self.COURSE_ID,
            self.PAYLOAD,
        )
        assert result == f"/img/course-assets/{self.COURSE_ID}/cover.png"
        assert fake.posted_url == (f"{self.SUPABASE_URL}/storage/v1/object/course-assets/{self.COURSE_ID}/cover.png")
        assert fake.posted_content == self.PAYLOAD

    def test_sends_required_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _install_fake_client(monkeypatch, _FakeResponse(201))
        ccu.upload_course_cover_bytes(
            self.SUPABASE_URL,
            self.SERVICE_KEY,
            self.COURSE_ID,
            self.PAYLOAD,
        )
        assert fake.posted_headers is not None
        assert fake.posted_headers["Authorization"] == f"Bearer {self.SERVICE_KEY}"
        # Supabase REST requires both ``Authorization`` and ``apikey`` for
        # service-role calls — dropping ``apikey`` returns 401 silently.
        assert fake.posted_headers["apikey"] == self.SERVICE_KEY
        # ``x-upsert: true`` is what makes the second upload of a cover
        # OVERWRITE the first instead of failing with "already exists".
        assert fake.posted_headers["x-upsert"] == "true"

    @pytest.mark.parametrize(
        "ext, expected_content_type, expected_object_ext",
        [
            ("png", "image/png", "png"),
            ("PNG", "image/png", "png"),
            (".jpg", "image/jpeg", "jpg"),
            ("jpeg", "image/jpeg", "jpeg"),
            ("webp", "image/webp", "webp"),
            ("gif", "image/gif", "gif"),
        ],
    )
    def test_known_extensions_map_to_content_type(
        self,
        monkeypatch: pytest.MonkeyPatch,
        ext: str,
        expected_content_type: str,
        expected_object_ext: str,
    ) -> None:
        fake = _install_fake_client(monkeypatch, _FakeResponse(200))
        result = ccu.upload_course_cover_bytes(
            self.SUPABASE_URL,
            self.SERVICE_KEY,
            self.COURSE_ID,
            self.PAYLOAD,
            ext=ext,
        )
        assert fake.posted_headers is not None
        assert fake.posted_headers["Content-Type"] == expected_content_type
        assert fake.posted_url is not None
        assert fake.posted_url.endswith(f"cover.{expected_object_ext}")
        assert result.endswith(f"cover.{expected_object_ext}")

    def test_unknown_extension_falls_back_to_png(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An unsupported extension (e.g. ``"tiff"``) collapses to
        ``png`` server-side so the on-disk object always has a content
        type we know how to serve. The frontend only ever uploads from
        the supported set, so this is purely defence-in-depth.
        """
        fake = _install_fake_client(monkeypatch, _FakeResponse(200))
        result = ccu.upload_course_cover_bytes(
            self.SUPABASE_URL,
            self.SERVICE_KEY,
            self.COURSE_ID,
            self.PAYLOAD,
            ext="tiff",
        )
        assert fake.posted_url is not None
        assert fake.posted_url.endswith("cover.png")
        assert result.endswith("cover.png")

    def test_trailing_slash_on_supabase_url_is_normalised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _install_fake_client(monkeypatch, _FakeResponse(200))
        ccu.upload_course_cover_bytes(
            self.SUPABASE_URL + "/",
            self.SERVICE_KEY,
            self.COURSE_ID,
            self.PAYLOAD,
        )
        assert fake.posted_url is not None
        # No accidental double-slash between origin and ``/storage/v1/...``.
        assert "//storage/v1/" not in fake.posted_url

    def test_non_2xx_raises_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_fake_client(monkeypatch, _FakeResponse(500, "Storage backend exploded"))
        with pytest.raises(RuntimeError) as exc:
            ccu.upload_course_cover_bytes(
                self.SUPABASE_URL,
                self.SERVICE_KEY,
                self.COURSE_ID,
                self.PAYLOAD,
            )
        # The error message must surface both the status code and the
        # body prefix so the caller has something to log; without that
        # an upload outage looks like a 500 with no signal.
        assert "500" in str(exc.value)
        assert "Storage backend exploded" in str(exc.value)

    def test_404_also_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A missing bucket comes back as 404, not 5xx — also a failure."""
        _install_fake_client(monkeypatch, _FakeResponse(404, "Bucket not found"))
        with pytest.raises(RuntimeError):
            ccu.upload_course_cover_bytes(
                self.SUPABASE_URL,
                self.SERVICE_KEY,
                self.COURSE_ID,
                self.PAYLOAD,
            )


def test_bucket_constant_matches_frontend_path() -> None:
    """The bucket name is wired into the public URL shape; a rename
    server-side without updating the frontend would break every existing
    cover. Pin the constant so the rename is a deliberate two-step.
    """
    assert ccu.COURSE_ASSETS_BUCKET == "course-assets"
    assert ccu.public_img_path_for_course_cover("X", "png").startswith(f"/img/{ccu.COURSE_ASSETS_BUCKET}/")
