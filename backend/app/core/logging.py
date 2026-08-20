import contextvars
import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request

# Per-request correlation. Vercel populates ``x-vercel-id`` on every
# inbound request; main.log_requests middleware copies it here so the
# DatadogHTTPHandler can stitch a WARNING/ERROR log to the originating
# RUM session that triggered the request.
vercel_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("vercel_request_id", default=None)


class DatadogHTTPHandler(logging.Handler):
    """Ship WARNING+ records straight to Datadog's HTTP logs intake.

    There is no Datadog Agent on Vercel serverless, so the handler does
    its own HTTPS POST per record. WARNING+ traffic is low enough that
    the small per-error latency is acceptable; INFO logs stay on stdout
    where Vercel's own log viewer captures them.

    "Low enough" held until it did not. On 2026-08-20 the translation
    provider began refusing every call, and the worker logged one warning
    per row at roughly a hundred a minute for hours — all of them the
    same sentence with a different id in it. Log indexing stopped that
    morning and did not come back: the intake still answers 202, and
    nothing submitted since is searchable. Production ran blind for
    eleven hours, and the outage that caused it had to be diagnosed out
    of the database instead.

    Worse than the silence was what the silence looked like. The
    error-spike monitor reported *recovered* seven minutes into the
    outage — not because the errors had stopped but because the logs
    had. A monitor that goes quiet when its data dies reads exactly like
    a monitor with nothing to report.

    So repeats are collapsed. Records are grouped by their format string
    — the template before the arguments are filled in — because that is
    what makes a burst a burst: one kind of event, a thousand ids. The
    first of a kind ships at once; the rest are counted, and the count
    rides on the next one that ships, so nothing is lost, only folded.
    """

    _REENTRY_GUARD_ATTR = "_dd_inside_emit"

    #: How long one kind of record holds the floor. A worker tick lasts
    #: 180 seconds, so a minute is short enough to keep a real, ongoing
    #: problem visible three times per tick and long enough that a burst
    #: costs three lines rather than three hundred.
    REPEAT_WINDOW_SECONDS = 60.0

    #: Distinct templates tracked at once. A bound, not a tuning knob:
    #: without it a process that logs from a loop with a computed format
    #: string would grow this dict without limit. Far above the number of
    #: distinct warnings this codebase can emit.
    MAX_TRACKED_TEMPLATES = 512

    def __init__(
        self,
        api_key: str,
        site: str,
        service: str,
        env: str,
        version: str,
        vercel_region: str,
    ) -> None:
        super().__init__()
        self.api_key = api_key
        self.service = service
        self.env = env
        self.version = version
        self.vercel_region = vercel_region
        self.endpoint = f"https://http-intake.logs.{site}/api/v2/logs"
        # Guarded by ``_repeat_lock``: the translation executor emits from
        # a thread pool, which is precisely where the burst came from.
        self._repeat_lock = threading.Lock()
        self._last_shipped: dict[tuple[str, int, str], float] = {}
        self._suppressed: dict[tuple[str, int, str], int] = {}

    def _hold_or_ship(self, record: logging.LogRecord) -> int | None:
        """``None`` to hold this record, otherwise how many were folded.

        Keyed on the *template* (``record.msg``, before ``%`` arguments
        are applied) rather than the formatted line, because a burst is
        one sentence with a thousand different ids in it. Keying on the
        formatted message would make every record unique and collapse
        nothing.
        """
        key = (record.name, record.levelno, str(record.msg)[:200])
        now = time.monotonic()
        with self._repeat_lock:
            last = self._last_shipped.get(key)
            if last is not None and now - last < self.REPEAT_WINDOW_SECONDS:
                self._suppressed[key] = self._suppressed.get(key, 0) + 1
                return None
            if last is None and len(self._last_shipped) >= self.MAX_TRACKED_TEMPLATES:
                # Full, and this template is new. Ship it rather than
                # hold it: dropping an unseen kind of warning to protect
                # a bookkeeping dict would be the wrong way round.
                return 0
            self._last_shipped[key] = now
            return self._suppressed.pop(key, 0)

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, self._REENTRY_GUARD_ATTR, False):
            return
        folded = self._hold_or_ship(record)
        if folded is None:
            return
        try:
            tags = [
                f"env:{self.env}",
                f"service:{self.service}",
                f"version:{self.version}",
                f"vercel_region:{self.vercel_region}",
            ]
            payload: dict[str, object] = {
                "ddsource": "python",
                "ddtags": ",".join(tags),
                "service": self.service,
                "hostname": f"vercel-{self.vercel_region}",
                "message": self.format(record),
                "status": record.levelname.lower(),
                "logger.name": record.name,
            }
            if folded:
                # Said out loud in the message as well as in a field: a
                # reader scanning the log stream must see that this line
                # stands for many, without having to know the schema.
                payload["message"] = f"{payload['message']}  [+{folded} more like this in the last minute]"
                payload["dd.suppressed_repeats"] = folded
            req_id = vercel_request_id.get()
            if req_id:
                payload["vercel.request_id"] = req_id
            if record.exc_info and self.formatter:
                exc_type = record.exc_info[0]
                if exc_type is not None:
                    payload["error.kind"] = exc_type.__name__
                payload["error.stack"] = self.formatter.formatException(record.exc_info)
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.endpoint,
                data=body,
                headers={"DD-API-KEY": self.api_key, "Content-Type": "application/json"},
                method="POST",
            )
            setattr(record, self._REENTRY_GUARD_ATTR, True)
            # 0.5s cap: this POST runs inline on the request thread for every
            # WARNING+ record, so under an error burst a slow Datadog intake
            # could stack-block requests. A tight timeout bounds that; losing
            # a log line on a slow intake is preferable to adding latency to
            # a user request. (A background QueueListener would drop logs on
            # Vercel serverless — the function freezes before it drains.)
            urllib.request.urlopen(req, timeout=0.5)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            # Best effort. Losing a log record is preferable to crashing the request.
            pass
        finally:
            setattr(record, self._REENTRY_GUARD_ATTR, False)


def setup_logging() -> None:
    """Configure structured logging for the application."""
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)

    api_key = os.environ.get("DD_API_KEY")
    dd_env = os.environ.get("DD_ENV")
    # BOTH keys must be explicitly set. DD_ENV used to default to
    # "production", which meant any machine with a User-scoped DD_API_KEY
    # (e.g. the dev box) shipped local pytest ERRORs tagged env:production —
    # they passed the prod error-spike monitor's filter and fired a false
    # alert (observed 2026-06-11). Prod sets both vars in Vercel env.
    if api_key and dd_env:
        version = (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "dev")[:7]
        dd_handler = DatadogHTTPHandler(
            api_key=api_key,
            site=os.environ.get("DD_SITE", "datadoghq.com"),
            service=os.environ.get("DD_SERVICE", "equip-backend"),
            env=dd_env,
            version=version,
            vercel_region=os.environ.get("VERCEL_REGION", "unknown"),
        )
        dd_handler.setLevel(logging.WARNING)
        dd_handler.setFormatter(formatter)
        root.addHandler(dd_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
