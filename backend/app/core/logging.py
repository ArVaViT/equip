import json
import logging
import os
import sys
import urllib.error
import urllib.request


class DatadogHTTPHandler(logging.Handler):
    """Ship WARNING+ records straight to Datadog's HTTP logs intake.

    There is no Datadog Agent on Vercel serverless, so the handler does
    its own HTTPS POST per record. WARNING+ traffic is low enough that
    the small per-error latency is acceptable; INFO logs stay on stdout
    where Vercel's own log viewer captures them.
    """

    _REENTRY_GUARD_ATTR = "_dd_inside_emit"

    def __init__(self, api_key: str, site: str, service: str, env: str, version: str) -> None:
        super().__init__()
        self.api_key = api_key
        self.service = service
        self.env = env
        self.version = version
        self.endpoint = f"https://http-intake.logs.{site}/api/v2/logs"

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, self._REENTRY_GUARD_ATTR, False):
            return
        try:
            payload = {
                "ddsource": "python",
                "ddtags": f"env:{self.env},service:{self.service},version:{self.version}",
                "service": self.service,
                "hostname": "vercel",
                "message": self.format(record),
                "status": record.levelname.lower(),
                "logger.name": record.name,
            }
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
            urllib.request.urlopen(req, timeout=2)
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
    if api_key:
        version = (os.environ.get("VERCEL_GIT_COMMIT_SHA") or "dev")[:7]
        dd_handler = DatadogHTTPHandler(
            api_key=api_key,
            site=os.environ.get("DD_SITE", "datadoghq.com"),
            service=os.environ.get("DD_SERVICE", "biblie-school-backend"),
            env=os.environ.get("DD_ENV", "production"),
            version=version,
        )
        dd_handler.setLevel(logging.WARNING)
        dd_handler.setFormatter(formatter)
        root.addHandler(dd_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
