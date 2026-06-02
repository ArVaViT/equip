"""Unit tests for ``app.services.daily_challenge.llm.GeminiPromptClient``.

The orchestrator tests in ``test_daily_challenge_orchestrator.py`` mock
``GeminiPromptClient.invoke`` so the wrapper itself was previously
untested. This file pins the HTTP shape, retry policy, error
classification, and response parsing of the client directly.

Pinned behaviours:

* **Constructor + lifecycle** — empty API key is a config bug, raised
  loudly; context-manager semantics; the ``_owns_client`` flag so
  external clients passed in are not closed underneath the caller.
* **Request shape** — URL builds correctly for default + custom model;
  ``X-goog-api-key`` carries the secret; ``generationConfig`` toggles
  ``responseMimeType`` when ``expect_json`` is set; ``systemInstruction``
  + ``contents`` carry the prompts.
* **Retry policy** — 200 returns immediately; 429 / 500 / 502 / 503 /
  504 / 408 retry up to ``max_retries``; non-retryable 4xx raises
  ``LLMError`` immediately; ``httpx.HTTPError`` (transport) retries
  then raises; exceeding ``max_retries`` raises ``LLMError``.
* **JSON path** — successful JSON parse returns dict; invalid JSON
  inside a 200 response raises ``LLMError``.
* **`_parse_text`** — empty candidates, malformed body shape,
  non-``STOP`` finishReason, empty text — each raises ``LLMError``
  with a useful message.

All paths are exercised offline via a stub ``httpx.Client`` so the
suite stays free of network and Gemini quota.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from app.services.daily_challenge.llm import GeminiPromptClient, LLMError

if TYPE_CHECKING:
    from collections.abc import Callable


class _FakeResponse:
    def __init__(self, *, status_code: int, json_body: Any | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.text = text or (json.dumps(json_body) if json_body is not None else "")

    def json(self) -> Any:
        return self._json_body


def _ok_body(text: str) -> dict:
    """Shape a Gemini-style ``generateContent`` 200 response."""
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": text}]},
                "finishReason": "STOP",
            }
        ]
    }


class _RecordingClient:
    """Stub for ``httpx.Client`` — records every ``post`` and replays a
    queue of responses (or raises queued exceptions in order).
    """

    def __init__(self, behaviour: list[Callable[..., _FakeResponse]]) -> None:
        self._behaviour = list(behaviour)
        self.posts: list[dict[str, Any]] = []
        self.closed = False

    def post(self, url: str, *, json: dict | None = None, headers: dict | None = None) -> _FakeResponse:
        self.posts.append({"url": url, "json": json, "headers": headers})
        if not self._behaviour:
            raise AssertionError("No more queued responses")
        next_step = self._behaviour.pop(0)
        return next_step()

    def close(self) -> None:
        self.closed = True


def _respond(body: Any, *, status: int = 200) -> Callable[..., _FakeResponse]:
    def factory() -> _FakeResponse:
        return _FakeResponse(status_code=status, json_body=body, text=json.dumps(body))

    return factory


def _respond_text(text: str, *, status: int) -> Callable[..., _FakeResponse]:
    def factory() -> _FakeResponse:
        return _FakeResponse(status_code=status, text=text)

    return factory


def _raise(exc: Exception) -> Callable[..., _FakeResponse]:
    def factory() -> _FakeResponse:
        raise exc

    return factory


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``time.sleep`` in the SUT module so retries don't waste
    real seconds. We don't care about the back-off timing here — the
    retry COUNT is what the tests assert."""
    import app.services.daily_challenge.llm as llm_module

    monkeypatch.setattr(llm_module.time, "sleep", lambda *_a, **_k: None)


class TestConstructor:
    def test_empty_api_key_raises(self) -> None:
        with pytest.raises(ValueError):
            GeminiPromptClient(api_key="")

    def test_passes_external_client_through_without_owning(self) -> None:
        """When the caller passes in their own ``httpx.Client`` we MUST
        NOT close it from ``__exit__`` / ``close`` — the caller's
        lifecycle owns it. This pin matters for shared-client patterns.
        """
        external = _RecordingClient(behaviour=[])
        client = GeminiPromptClient(api_key="k", client=external)  # type: ignore[arg-type]
        client.close()
        assert external.closed is False

    def test_owns_client_when_none_provided(self) -> None:
        """Conversely, when we created the client we MUST close it on
        ``close()`` so a long-running cron worker doesn't accumulate
        sockets across orchestrator runs.
        """
        c = GeminiPromptClient(api_key="k")
        # Swap in a recording client so we can observe close() without
        # actually opening a TCP socket in CI.
        external = _RecordingClient(behaviour=[])
        c._client = external  # type: ignore[assignment]
        c._owns_client = True
        c.close()
        assert external.closed is True


class TestContextManager:
    def test_enter_returns_self(self) -> None:
        with GeminiPromptClient(api_key="k") as c:
            assert isinstance(c, GeminiPromptClient)

    def test_exit_closes_owned_client(self) -> None:
        c = GeminiPromptClient(api_key="k")
        external = _RecordingClient(behaviour=[])
        c._client = external  # type: ignore[assignment]
        c.__exit__(None, None, None)
        assert external.closed is True


class TestInvokeRequestShape:
    """Make sure the request bytes match what Gemini's
    ``generateContent`` endpoint expects.
    """

    def test_default_model_used_when_omitted(self) -> None:
        recorder = _RecordingClient(behaviour=[_respond(_ok_body("hello"))])
        client = GeminiPromptClient(api_key="secret", client=recorder)  # type: ignore[arg-type]
        client.invoke(system="sys", user="user")
        assert "gemini-2.5-flash-lite" in recorder.posts[0]["url"]
        assert recorder.posts[0]["url"].endswith(":generateContent")

    def test_custom_model_in_url(self) -> None:
        recorder = _RecordingClient(behaviour=[_respond(_ok_body("hi"))])
        client = GeminiPromptClient(api_key="secret", client=recorder)  # type: ignore[arg-type]
        client.invoke(system="sys", user="user", model="gemini-2.5-pro")
        assert "/models/gemini-2.5-pro:generateContent" in recorder.posts[0]["url"]

    def test_api_key_in_header(self) -> None:
        recorder = _RecordingClient(behaviour=[_respond(_ok_body("hi"))])
        client = GeminiPromptClient(api_key="secret-xyz", client=recorder)  # type: ignore[arg-type]
        client.invoke(system="sys", user="user")
        assert recorder.posts[0]["headers"]["X-goog-api-key"] == "secret-xyz"

    def test_payload_carries_system_and_user_prompts(self) -> None:
        recorder = _RecordingClient(behaviour=[_respond(_ok_body("hi"))])
        client = GeminiPromptClient(api_key="k", client=recorder)  # type: ignore[arg-type]
        client.invoke(system="SYS-PROMPT", user="USER-PROMPT", temperature=0.3)
        payload = recorder.posts[0]["json"]
        assert payload["systemInstruction"]["parts"][0]["text"] == "SYS-PROMPT"
        assert payload["contents"][0]["parts"][0]["text"] == "USER-PROMPT"
        assert payload["contents"][0]["role"] == "user"
        assert payload["generationConfig"]["temperature"] == 0.3

    def test_expect_json_sets_response_mime_type(self) -> None:
        recorder = _RecordingClient(behaviour=[_respond(_ok_body('{"k":"v"}'))])
        client = GeminiPromptClient(api_key="k", client=recorder)  # type: ignore[arg-type]
        result = client.invoke(system="s", user="u", expect_json=True)
        assert recorder.posts[0]["json"]["generationConfig"]["responseMimeType"] == "application/json"
        assert result == {"k": "v"}

    def test_expect_json_false_returns_raw_text(self) -> None:
        recorder = _RecordingClient(behaviour=[_respond(_ok_body("hello world"))])
        client = GeminiPromptClient(api_key="k", client=recorder)  # type: ignore[arg-type]
        result = client.invoke(system="s", user="u", expect_json=False)
        assert result == "hello world"
        # responseMimeType only set when expect_json is True.
        assert "responseMimeType" not in recorder.posts[0]["json"]["generationConfig"]


class TestInvokeRetryPolicy:
    def test_200_returns_immediately(self) -> None:
        recorder = _RecordingClient(behaviour=[_respond(_ok_body("ok"))])
        client = GeminiPromptClient(api_key="k", client=recorder, max_retries=3)  # type: ignore[arg-type]
        assert client.invoke(system="s", user="u") == "ok"
        assert len(recorder.posts) == 1

    @pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
    def test_retryable_statuses_are_retried(self, status: int) -> None:
        """Each transient HTTP failure is retried up to ``max_retries``
        times; if a later attempt succeeds we return that result.
        """
        recorder = _RecordingClient(
            behaviour=[
                _respond_text("transient", status=status),
                _respond(_ok_body("recovered")),
            ]
        )
        client = GeminiPromptClient(api_key="k", client=recorder, max_retries=2)  # type: ignore[arg-type]
        assert client.invoke(system="s", user="u") == "recovered"
        assert len(recorder.posts) == 2

    def test_non_retryable_4xx_raises_immediately(self) -> None:
        """A 400 (bad request) is a programmer error — no point
        retrying. The client surfaces the error rather than burning
        through the retry budget.
        """
        recorder = _RecordingClient(
            behaviour=[
                _respond_text("bad request", status=400),
            ]
        )
        client = GeminiPromptClient(api_key="k", client=recorder, max_retries=3)  # type: ignore[arg-type]
        with pytest.raises(LLMError) as exc:
            client.invoke(system="s", user="u")
        assert "400" in str(exc.value)
        assert len(recorder.posts) == 1

    def test_403_is_not_retried(self) -> None:
        recorder = _RecordingClient(behaviour=[_respond_text("forbidden", status=403)])
        client = GeminiPromptClient(api_key="k", client=recorder, max_retries=3)  # type: ignore[arg-type]
        with pytest.raises(LLMError):
            client.invoke(system="s", user="u")
        assert len(recorder.posts) == 1

    def test_httpx_transport_error_retries_then_raises(self) -> None:
        """Network-layer errors get the same retry treatment as 429/5xx.
        On exhaustion we raise LLMError with the underlying cause."""
        recorder = _RecordingClient(
            behaviour=[
                _raise(httpx.ConnectError("connection refused")),
                _raise(httpx.ConnectError("connection refused")),
                _raise(httpx.ConnectError("connection refused")),
            ]
        )
        client = GeminiPromptClient(api_key="k", client=recorder, max_retries=2)  # type: ignore[arg-type]
        with pytest.raises(LLMError) as exc:
            client.invoke(system="s", user="u")
        assert "after retries" in str(exc.value)
        # max_retries=2 -> 3 attempts total (initial + 2 retries).
        assert len(recorder.posts) == 3

    def test_max_retries_exceeded_raises(self) -> None:
        recorder = _RecordingClient(
            behaviour=[
                _respond_text("a", status=503),
                _respond_text("b", status=503),
                _respond_text("c", status=503),
            ]
        )
        client = GeminiPromptClient(api_key="k", client=recorder, max_retries=2)  # type: ignore[arg-type]
        with pytest.raises(LLMError):
            client.invoke(system="s", user="u")
        assert len(recorder.posts) == 3


class TestInvokeJsonPath:
    def test_invalid_json_with_expect_json_raises_llm_error(self) -> None:
        """When ``expect_json=True`` and the model honours
        ``responseMimeType`` but somehow returns non-JSON anyway, we
        surface it as LLMError so the orchestrator records the failure
        rather than persisting garbage.
        """
        recorder = _RecordingClient(behaviour=[_respond(_ok_body("not actually json"))])
        client = GeminiPromptClient(api_key="k", client=recorder)  # type: ignore[arg-type]
        with pytest.raises(LLMError) as exc:
            client.invoke(system="s", user="u", expect_json=True)
        assert "non-JSON" in str(exc.value)


class TestParseText:
    """Direct unit tests on the static parser — these mirror the malformed
    payload shapes Gemini has shipped in the wild.
    """

    def test_happy_path_returns_joined_text(self) -> None:
        body = {
            "candidates": [
                {
                    "content": {"parts": [{"text": "first "}, {"text": "second"}]},
                    "finishReason": "STOP",
                }
            ]
        }
        assert GeminiPromptClient._parse_text(body) == "first second"

    def test_no_candidates_raises(self) -> None:
        with pytest.raises(LLMError) as exc:
            GeminiPromptClient._parse_text({"candidates": []})
        assert "no candidates" in str(exc.value)

    def test_missing_candidates_key_raises(self) -> None:
        with pytest.raises(LLMError):
            GeminiPromptClient._parse_text({})

    def test_finish_reason_safety_raises_with_truncation_hint(self) -> None:
        """``finishReason='SAFETY'`` or ``MAX_TOKENS`` means the model
        stopped early. Raising surfaces the issue rather than letting
        truncated content slip through as a 'valid' answer."""
        body = {
            "candidates": [
                {
                    "content": {"parts": [{"text": "truncated..."}]},
                    "finishReason": "MAX_TOKENS",
                }
            ]
        }
        with pytest.raises(LLMError) as exc:
            GeminiPromptClient._parse_text(body)
        assert "MAX_TOKENS" in str(exc.value)
        assert "truncated output" in str(exc.value)

    def test_empty_text_raises(self) -> None:
        body = {"candidates": [{"content": {"parts": []}, "finishReason": "STOP"}]}
        with pytest.raises(LLMError) as exc:
            GeminiPromptClient._parse_text(body)
        assert "empty" in str(exc.value)

    def test_malformed_candidate_shape_raises(self) -> None:
        """When ``candidates[0]`` is the wrong type the AttributeError /
        KeyError / TypeError catch path fires and we surface a clean
        LLMError instead of leaking the underlying exception."""
        body = {"candidates": ["not a dict"]}
        with pytest.raises(LLMError) as exc:
            GeminiPromptClient._parse_text(body)
        assert "malformed candidate" in str(exc.value)

    def test_no_finish_reason_is_accepted(self) -> None:
        """Some preview models omit ``finishReason`` entirely. When the
        text is non-empty we accept that — the guard only fires when a
        non-STOP reason is present."""
        body = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
        assert GeminiPromptClient._parse_text(body) == "ok"
