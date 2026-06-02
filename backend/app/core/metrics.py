"""Datadog metric emission via structured log lines.

Vercel serverless workers can't run a StatsD daemon and the
Datadog Python SDK's HTTP submitter would add per-request latency.
Instead we emit structured log lines that Datadog's log-based
metrics feature parses into time series.

The log shape:

    INFO equip.metric.<name> value=<float> [tag=value...]

Datadog log search queries pick these up via the
``@metric:<name> @value:*`` filter, with extracted attributes
(course_id, teacher_id, locale, etc.) becoming filterable
dimensions. The dashboards in ``docs/datadog/*.json`` reference
these metric names directly.

This module is import-cheap, side-effect-free at import time, and
graceful when ``DD_API_KEY`` is unset (the underlying logger still
runs — the log just lands in stdout, not Datadog — so the local
dev experience is unaffected).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("equip.metric")


def emit(name: str, value: float = 1.0, **tags: Any) -> None:
    """Emit a single metric data point.

    Parameters
    ----------
    name : str
        Metric name in ``equip.<group>.<measurement>`` shape (e.g.,
        ``equip.grading.pending`` or
        ``equip.activity.daily_active_users``). The dashboards in
        ``docs/datadog/*.json`` assume this exact prefix.
    value : float, default 1.0
        Numeric value. Counter increments pass ``1.0``; gauges pass
        the current measurement; timings pass milliseconds.
    **tags
        Arbitrary key=value tags that become Datadog log
        attributes. Common ones: ``course_id``, ``teacher_id``,
        ``locale``, ``user_id``.

    The function is non-raising — a logging failure must NEVER break
    the calling request path. Datadog dashboards going dark for a
    minute is fine; a 500 because emission failed is not.
    """
    try:
        # Tag string in a form Datadog's log-based-metric pipeline
        # picks up as separate attributes (`key=value` pairs
        # space-separated). Empty values are dropped to avoid
        # creating a flood of ``=`` keys.
        tag_str = " ".join(f"{k}={v}" for k, v in tags.items() if v is not None and v != "")
        if tag_str:
            logger.info("%s value=%s %s", name, value, tag_str)
        else:
            logger.info("%s value=%s", name, value)
    except Exception:
        # Don't even log the error here; the calling site will have
        # its own log line for whatever it was doing. We swallow.
        return


def increment(name: str, **tags: Any) -> None:
    """Counter convenience — same as ``emit(name, 1.0, **tags)``."""
    emit(name, 1.0, **tags)


def gauge(name: str, value: float, **tags: Any) -> None:
    """Gauge convenience — explicit about non-counter intent."""
    emit(name, value, **tags)


def timing(name: str, milliseconds: float, **tags: Any) -> None:
    """Timing convenience — same wire shape; the suffix on
    ``name`` (e.g., ``.p50`` or ``.time_to_grade``) signals the
    aggregation Datadog will apply on the dashboard side.
    """
    emit(name, milliseconds, **tags)


__all__ = ["emit", "gauge", "increment", "timing"]
