"""Per-request access log and request id, so a slow or failing call can be found in CloudWatch.

One line per request, as JSON, e.g. ``{"method": "POST", "path": "/projects", "status": 201, "ms": 42, "request_id": "..."}``.
Tail it with ``aws logs tail /aws/lambda/<function> --follow`` (see docs/TESTING.md). The query string, headers and body are
never logged, so tokens and search text stay out of the logs. The same id is returned to the caller in ``X-Request-Id``.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

access_logger = logging.getLogger("pm_api.access")


def configure_logging() -> None:
    """Make INFO lines (access log, migrations) visible: Lambda's default level is WARNING, uvicorn has no handler."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for name in ("pm_api", "app"):
        logging.getLogger(name).setLevel(logging.INFO)


class RequestLogMiddleware:
    """Outermost ASGI middleware: times the whole request and logs its final status."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        request_id = dict(scope.get("headers", [])).get(b"x-request-id", b"").decode("ascii", "ignore")[:64] or uuid.uuid4().hex
        status = 500

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                header = (b"x-request-id", request_id.encode("ascii", "ignore"))
                message = {**message, "headers": [*message.get("headers", []), header]}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            access_logger.info(json.dumps({
                "method": scope["method"], "path": scope["path"], "status": status,
                "ms": round((time.perf_counter() - started) * 1000), "request_id": request_id,
            }))
