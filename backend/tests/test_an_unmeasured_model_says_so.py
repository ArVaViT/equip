"""Both Gemini models are guarded, and the guard quotes the price.

``GEMINI_MODEL`` has warned about an unmeasured model since production
spent 81 days on ``gemini-flash-latest`` without anyone noticing.
``GEMINI_REVIEW_MODEL`` had no guard at all — and it is the worse one to
leave open:

* It is not set in Vercel. It runs on whatever this repository's default
  says, which means a code change moves it with nothing in the
  environment to compare against.
* It is the expensive model. $0.30 per million input tokens against the
  translator's $0.10, and $2.50 per million output against $0.40 — 3x
  and 6.25x.
* Thinking tokens bill as output. Point the reviewer at a model that
  thinks and the hidden tokens land at $2.50 per million.

So the warning names prices rather than saying "unverified". Nobody
looks up what "unverified" costs.
"""

from __future__ import annotations

import logging

from app.core.config import MEASURED_GEMINI_MODELS, Settings, describe_measured_gemini_models


def _settings(monkeypatch, **env: str) -> Settings:
    for var in ("GEMINI_MODEL", "GEMINI_REVIEW_MODEL"):
        monkeypatch.delenv(var, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def test_the_models_this_repository_ships_are_both_measured(monkeypatch) -> None:
    """A default that trips its own guard would teach the reader to
    ignore the warning, which is the only way this guard can fail."""
    settings = _settings(monkeypatch)
    assert settings.GEMINI_MODEL in MEASURED_GEMINI_MODELS
    assert settings.GEMINI_REVIEW_MODEL in MEASURED_GEMINI_MODELS


def test_a_deployment_on_the_measured_models_boots_quietly(monkeypatch, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        _settings(monkeypatch)
    assert not [r for r in caplog.records if "measured models" in r.getMessage()]


def test_an_unmeasured_review_model_is_named_out_loud(monkeypatch, caplog) -> None:
    """The finding this test exists for: the reviewer could be pointed at
    any model at all and nothing anywhere said a word."""
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        _settings(monkeypatch, GEMINI_REVIEW_MODEL="gemini-3.0-pro")
    warnings = [r.getMessage() for r in caplog.records]
    assert any("GEMINI_REVIEW_MODEL" in m and "gemini-3.0-pro" in m for m in warnings)
    assert not any("GEMINI_MODEL is" in m for m in warnings)


def test_an_unmeasured_translation_model_still_says_so(monkeypatch, caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        _settings(monkeypatch, GEMINI_MODEL="gemini-flash-latest")
    warnings = [r.getMessage() for r in caplog.records]
    assert any("GEMINI_MODEL is" in m and "gemini-flash-latest" in m for m in warnings)


def test_the_warning_says_what_the_measured_models_cost(monkeypatch, caplog) -> None:
    """The word "unverified" is a word. "$2.50/M out" is a reason to look."""
    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        _settings(monkeypatch, GEMINI_REVIEW_MODEL="gemini-3.0-pro")
    warnings = [r.getMessage() for r in caplog.records]
    assert any("$2.50/M out" in m for m in warnings)
    assert any("$0.10/M in" in m for m in warnings)


def test_the_priced_table_and_the_rendered_line_cannot_drift(monkeypatch) -> None:
    rendered = describe_measured_gemini_models()
    for model in MEASURED_GEMINI_MODELS:
        assert model in rendered


def test_a_review_model_blanked_in_the_environment_falls_back(monkeypatch) -> None:
    """Vercel lets a variable be set to the empty string, and an empty
    model id goes into the URL as ``models/:generateContent`` — a 404 on
    every review, silently turning the reader off. ``GEMINI_MODEL``
    already guarded against this; the reviewer did not."""
    settings = _settings(monkeypatch, GEMINI_REVIEW_MODEL="   ")
    assert settings.GEMINI_REVIEW_MODEL == "gemini-3.5-flash-lite"
