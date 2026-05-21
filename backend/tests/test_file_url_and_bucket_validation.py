"""Schema-level validation for the file_url + file_bucket attack surfaces.

A teacher viewing a student submission opens ``file_url`` via
``<a target="_blank">``. Accepting ``javascript:`` / ``data:`` schemes
turns student input into stored XSS against the grader.

A chapter block carries ``{file_bucket, file_path}`` that the frontend
later signs into a download URL. Without an allowlist on ``file_bucket``,
a teacher could plant a block pointing at the ``avatars`` bucket and
mint signed URLs against another tenant's objects. Path-traversal
segments in ``file_path`` are similarly defense-in-depth.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.assignment import SubmissionCreate
from app.schemas.chapter_block import BlockCreate, BlockUpdate


class TestSubmissionFileUrl:
    def test_https_url_is_accepted(self):
        SubmissionCreate(file_url="https://example.com/work.pdf")

    def test_none_is_accepted(self):
        SubmissionCreate(file_url=None)

    def test_empty_string_normalizes_to_none(self):
        result = SubmissionCreate(file_url="")
        assert result.file_url is None

    def test_javascript_scheme_is_rejected(self):
        with pytest.raises(ValidationError):
            SubmissionCreate(file_url="javascript:alert(document.cookie)")

    def test_data_scheme_is_rejected(self):
        with pytest.raises(ValidationError):
            SubmissionCreate(file_url="data:text/html,<script>alert(1)</script>")

    def test_http_is_rejected_no_mixed_content(self):
        with pytest.raises(ValidationError):
            SubmissionCreate(file_url="http://example.com/insecure.pdf")

    def test_scheme_relative_url_is_rejected(self):
        with pytest.raises(ValidationError):
            SubmissionCreate(file_url="//evil.example/x")

    def test_vbscript_scheme_is_rejected(self):
        with pytest.raises(ValidationError):
            SubmissionCreate(file_url="vbscript:msgbox(1)")


class TestBlockFileBucket:
    def test_course_materials_is_accepted(self):
        BlockCreate(block_type="file", file_bucket="course-materials", file_path="chapter/x.pdf")

    def test_none_is_accepted(self):
        BlockCreate(block_type="text", file_bucket=None)

    def test_avatars_bucket_rejected(self):
        with pytest.raises(ValidationError):
            BlockCreate(block_type="file", file_bucket="avatars", file_path="chapter/x.png")

    def test_arbitrary_bucket_name_rejected(self):
        with pytest.raises(ValidationError):
            BlockCreate(block_type="file", file_bucket="course-assets", file_path="chapter/x.png")

    def test_update_validates_too(self):
        with pytest.raises(ValidationError):
            BlockUpdate(file_bucket="avatars")


class TestBlockFilePath:
    def test_relative_path_is_accepted(self):
        BlockCreate(block_type="file", file_bucket="course-materials", file_path="chapter-id/123-name.pdf")

    def test_none_is_accepted(self):
        BlockCreate(block_type="text", file_path=None)

    def test_parent_segment_rejected(self):
        with pytest.raises(ValidationError):
            BlockCreate(block_type="file", file_bucket="course-materials", file_path="../etc/passwd")

    def test_parent_segment_anywhere_rejected(self):
        with pytest.raises(ValidationError):
            BlockCreate(
                block_type="file",
                file_bucket="course-materials",
                file_path="chapter/../../etc/passwd",
            )

    def test_leading_slash_rejected(self):
        with pytest.raises(ValidationError):
            BlockCreate(block_type="file", file_bucket="course-materials", file_path="/abs/path.pdf")

    def test_backslash_traversal_rejected(self):
        with pytest.raises(ValidationError):
            BlockCreate(block_type="file", file_bucket="course-materials", file_path="chapter\\..\\evil.pdf")
