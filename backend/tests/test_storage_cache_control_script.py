"""``scripts/storage_cache_control.py`` against a fake Storage.

It runs once, by hand, on production objects — so the parts that could do
damage are pinned here: it only touches the two public buckets, puts back
the same bytes and type under the same key, leaves an object that already
carries the header alone, and writes nothing on a dry run.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
from typing import Any

import httpx

_SPEC = importlib.util.spec_from_file_location(
    "storage_cache_control", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "storage_cache_control.py"
)
assert _SPEC and _SPEC.loader
script = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(script)


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, Any]] = {
            ("course-assets", "c1/cover-aaaa1111.png"): {"bytes": b"png", "type": "image/png", "cc": "no-cache"},
            ("course-assets", "content-images/1-bbbb.webp"): {
                "bytes": b"webp",
                "type": "image/webp",
                "cc": script.TARGET,
            },
            ("avatars", "u1/avatar-cccc.jpg"): {"bytes": b"jpg", "type": "image/jpeg", "cc": "public, 3600"},
        }
        self.puts: list[tuple[str, str, bytes, dict[str, str]]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
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
        bucket, key = path.removeprefix("/storage/v1/object/").split("/", 1)
        assert bucket in script.BUCKETS
        obj = self.objects[(bucket, key)]
        if request.method == "GET":
            return httpx.Response(200, content=obj["bytes"], headers={"content-type": obj["type"]})
        assert request.method == "PUT"
        self.puts.append((bucket, key, request.content, dict(request.headers)))
        obj.update(bytes=request.content, cc=request.headers["cache-control"], type=request.headers["content-type"])
        return httpx.Response(200, json={"Key": f"{bucket}/{key}"})


def _client(fake: FakeStorage) -> httpx.Client:
    return httpx.Client(base_url="https://x.supabase.co", transport=httpx.MockTransport(fake.handler))


def test_a_dry_run_writes_nothing() -> None:
    fake = FakeStorage()
    assert script.run(_client(fake), apply=False) == 0
    assert fake.puts == []


def test_apply_rewrites_only_the_stale_objects_with_the_same_bytes_and_type() -> None:
    fake = FakeStorage()
    assert script.run(_client(fake), apply=True) == 0
    written = {(b, k): (body, h) for b, k, body, h in fake.puts}
    assert set(written) == {("course-assets", "c1/cover-aaaa1111.png"), ("avatars", "u1/avatar-cccc.jpg")}
    body, headers = written[("course-assets", "c1/cover-aaaa1111.png")]
    assert body == b"png"
    assert headers["content-type"] == "image/png"
    assert headers["cache-control"] == "public, max-age=31536000, s-maxage=31536000, immutable"
    assert headers["x-upsert"] == "true"


def test_a_second_run_is_a_no_op() -> None:
    fake = FakeStorage()
    script.run(_client(fake), apply=True)
    fake.puts.clear()
    assert script.run(_client(fake), apply=True) == 0
    assert fake.puts == []
