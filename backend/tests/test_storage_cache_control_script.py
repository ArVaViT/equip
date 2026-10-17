"""``scripts/storage_cache_control.py`` against a fake Storage.

It runs once, by hand, on production objects — so the parts that could do
damage are pinned here: it only touches the two public buckets, puts back
the same bytes and type under the same key as a multipart upload with the
``cacheControl`` field Storage reads, leaves an object that already
carries the header alone, skips a type the bucket refuses instead of
failing on it, believes the served header rather than the row's metadata,
and writes nothing on a dry run.
"""

from __future__ import annotations

import email
import email.policy
import importlib.util
import json
import pathlib
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    import pytest

_SPEC = importlib.util.spec_from_file_location(
    "storage_cache_control", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "storage_cache_control.py"
)
assert _SPEC and _SPEC.loader
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)

RASTER = ["image/jpeg", "image/png", "image/webp", "image/gif"]


def _multipart_parts(request: httpx.Request) -> list[tuple[str, bytes, str | None]]:
    """``(field name, body, part content-type)`` in the order they were sent."""
    raw = b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.content
    message = email.message_from_bytes(raw, policy=email.policy.HTTP)
    parts = []
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        payload = part.get_payload(decode=True)
        body = payload if isinstance(payload, bytes) else b""
        parts.append((str(name), body, part.get_content_type() if filename else None))
    return parts


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, Any]] = {
            ("course-assets", "c1/cover-aaaa1111.png"): {"bytes": b"png", "type": "image/png", "cc": "no-cache"},
            ("course-assets", "content-images/1-bbbb.webp"): {
                "bytes": b"webp",
                "type": "image/webp",
                "cc": script.TARGET,
            },
            ("course-assets", "diagrams/four-steps.svg"): {
                "bytes": b"<svg/>",
                "type": "image/svg+xml",
                "cc": "no-cache",
            },
            ("avatars", "u1/avatar-cccc.jpg"): {
                "bytes": b"jpg",
                "type": "image/jpeg",
                # What the first version of this script left behind: the
                # row's metadata echoed the header, the object kept serving
                # ``no-cache``.
                "cc": "public, max-age=31536000, s-maxage=86400, immutable",
                "served": "no-cache",
            },
        }
        self.allowed: dict[str, list[str] | None] = {"course-assets": RASTER, "avatars": RASTER}
        self.puts: list[tuple[str, str, bytes, dict[str, str], list[tuple[str, bytes, str | None]]]] = []
        self.store_header = True  # False imitates a Storage that accepts the write and still serves no-cache

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith("/storage/v1/bucket/"):
            bucket = path.rsplit("/", 1)[1]
            return httpx.Response(200, json={"id": bucket, "public": True, "allowed_mime_types": self.allowed[bucket]})
        if path.startswith("/storage/v1/object/list/"):
            bucket = path.rsplit("/", 1)[1]
            prefix = json.loads(request.content)["prefix"]
            names: dict[str, dict[str, Any]] = {}
            for (b, key), obj in self.objects.items():
                if b != bucket or not key.startswith(prefix):
                    continue
                rest = key[len(prefix) :]
                head = rest.split("/", 1)[0]
                if "/" in rest:
                    names[head] = {"name": head, "id": None, "metadata": None}
                else:
                    names[head] = {
                        "name": head,
                        "id": "x",
                        "metadata": {"cacheControl": obj["cc"], "mimetype": obj["type"]},
                    }
            return httpx.Response(200, json=list(names.values()))
        if path.startswith("/storage/v1/object/public/"):
            bucket, key = path.removeprefix("/storage/v1/object/public/").split("/", 1)
            obj = self.objects[(bucket, key)]
            assert request.url.params.get("v"), "a served-header check must miss the CDN copy"
            served = obj.get("served", obj["cc"])
            return httpx.Response(
                200, content=obj["bytes"], headers={"cache-control": served, "content-type": obj["type"]}
            )
        bucket, key = path.removeprefix("/storage/v1/object/").split("/", 1)
        assert bucket in script.BUCKETS
        obj = self.objects[(bucket, key)]
        if request.method == "GET":
            return httpx.Response(200, content=obj["bytes"], headers={"content-type": obj["type"]})
        assert request.method == "PUT"
        parts = _multipart_parts(request)
        self.puts.append((bucket, key, request.content, dict(request.headers), parts))
        fields = {name: body for name, body, ctype in parts if ctype is None}
        (file_body, file_type) = next((body, ctype) for _, body, ctype in parts if ctype is not None)
        allowed = self.allowed[bucket]
        if allowed and file_type not in allowed:
            return httpx.Response(415, json={"statusCode": "415", "error": "invalid_mime_type"})
        cache_control = f"max-age={fields['cacheControl'].decode()}" if "cacheControl" in fields else "no-cache"
        obj.update(bytes=file_body, type=file_type, cc=cache_control)
        obj["served"] = cache_control if self.store_header else "no-cache"
        return httpx.Response(200, json={"Key": f"{bucket}/{key}"})


def _client(fake: FakeStorage) -> httpx.Client:
    return httpx.Client(base_url="https://x.supabase.co", transport=httpx.MockTransport(fake.handler))


def test_a_dry_run_writes_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeStorage()
    assert script.run(_client(fake), apply=False) == 0
    assert fake.puts == []
    assert (
        "skipped diagrams/four-steps.svg: image/svg+xml is not in the bucket's allowed_mime_types"
        in capsys.readouterr().out
    )


def test_apply_rewrites_only_the_stale_objects_with_the_same_bytes_and_type() -> None:
    fake = FakeStorage()
    assert script.run(_client(fake), apply=True) == 0
    written = {(b, k): (body, h, parts) for b, k, body, h, parts in fake.puts}
    assert set(written) == {("course-assets", "c1/cover-aaaa1111.png"), ("avatars", "u1/avatar-cccc.jpg")}
    _, headers, parts = written[("course-assets", "c1/cover-aaaa1111.png")]
    assert headers["x-upsert"] == "true"
    assert headers["content-type"].startswith("multipart/form-data")
    # The field first, then the file: Storage reads the field off the parts
    # it has already seen when the file arrives.
    assert parts == [("cacheControl", b"31536000", None), ("", b"png", "image/png")]
    assert fake.objects[("course-assets", "c1/cover-aaaa1111.png")]["served"] == "max-age=31536000"


def test_a_type_the_bucket_refuses_is_skipped_by_name_not_failed(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeStorage()
    assert script.run(_client(fake), apply=True) == 0
    assert ("course-assets", "diagrams/four-steps.svg") not in {(b, k) for b, k, *_ in fake.puts}
    assert "skipped diagrams/four-steps.svg: image/svg+xml" in capsys.readouterr().out


def test_a_415_from_storage_is_a_skip_too(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeStorage()
    fake.allowed["course-assets"] = None  # the bucket says anything goes, Storage still says no
    original = fake.handler

    def refusing(request: httpx.Request) -> httpx.Response:
        if request.method == "PUT" and request.url.path.endswith(".svg"):
            return httpx.Response(415, json={"statusCode": "415", "error": "invalid_mime_type"})
        return original(request)

    client = httpx.Client(base_url="https://x.supabase.co", transport=httpx.MockTransport(refusing))
    assert script.run(client, apply=True) == 0
    assert "skipped: Storage refused the type (image/svg+xml)" in capsys.readouterr().out


def test_the_served_header_is_believed_not_the_row_metadata(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeStorage()
    fake.store_header = False
    assert script.run(_client(fake), apply=True) == 2
    assert "written, but still served with 'no-cache'" in capsys.readouterr().err


def test_only_touches_the_one_object_named() -> None:
    fake = FakeStorage()
    assert script.run(_client(fake), apply=True, only="avatars/u1/avatar-cccc.jpg") == 0
    assert [(b, k) for b, k, *_ in fake.puts] == [("avatars", "u1/avatar-cccc.jpg")]


def test_a_second_run_is_a_no_op() -> None:
    fake = FakeStorage()
    script.run(_client(fake), apply=True)
    fake.puts.clear()
    assert script.run(_client(fake), apply=True) == 0
    assert fake.puts == []
