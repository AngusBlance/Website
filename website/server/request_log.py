"""Request logging: one row per HTTP request, with everything FastAPI sees about the
request *and* its response.

The middleware times the request, lets the app handle it, and only writes the log row
after the response body has been sent, in a background task. A page never waits for
logging (or for the ip-api.com location lookup), and a logging failure is logged and
never breaks the page.

What's stored (table raw.fast_api_requests):
  request   method, path, full url, scheme, http_version, query string + params, headers
            (as a dict, and as raw [name, value] pairs keeping duplicates/order), body,
            client ip/port, the ASGI scope (everything the server passes in)
  routing   the matched route template (e.g. /api/{path}), endpoint name, path params
  response  status code, headers, size in bytes, content type, error (if the app raised)
  timing    request_started_at (app clock, UTC, µs), time to response headers, total duration
  extra     ip-api.com location lookup for the client IP (in the background)

Privacy: secret headers (cookies, Authorization, tokens, ...) keep their name but the value
is stored as "[redacted]"; bodies over BODY_LIMIT bytes are not stored (size and content type are).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

BODY_LIMIT = 4096  # bytes of request body kept; bigger bodies store only size + content type
REDACTED = "[redacted]"
SECRET_HEADERS = frozenset({
    "cookie", "set-cookie", "authorization", "proxy-authorization", "x-api-key", "x-auth-token",
    "x-csrf-token", "x-xsrf-token", "cf-access-jwt-assertion",
})
SECRET_WORDS = ("token", "secret", "password", "session", "api-key", "apikey")

# Background logging tasks, kept referenced so they aren't garbage-collected mid-flight
_pending: set[asyncio.Task] = set()


def is_secret_header(name: str) -> bool:
    n = name.lower()
    return n in SECRET_HEADERS or any(word in n for word in SECRET_WORDS)


def redact_pairs(pairs: list[tuple[str, str]]) -> list[list[str]]:
    """[[name, value], ...] in the order received (duplicates kept), secret values redacted."""
    return [[name, REDACTED if is_secret_header(name) else value] for name, value in pairs]


def redact_dict(pairs: list[tuple[str, str]]) -> dict[str, str]:
    """{name: value}, duplicate names joined with ", " (like HTTP does), secret values redacted."""
    out: dict[str, str] = {}
    for name, value in redact_pairs(pairs):
        out[name] = f"{out[name]}, {value}" if name in out else value
    return out


def _decode_pairs(raw: list[tuple[bytes, bytes]]) -> list[tuple[str, str]]:
    return [(k.decode("latin-1").lower(), v.decode("latin-1")) for k, v in raw]


def body_fields(body: bytes, content_type: str | None) -> dict[str, Any]:
    """The request body as JSON (if it parses) or text, unless it's over BODY_LIMIT bytes."""
    fields: dict[str, Any] = {"body_size": len(body), "body_content_type": content_type,
                              "body_truncated": len(body) > BODY_LIMIT, "body": None}
    if not body or fields["body_truncated"]:
        return fields
    try:
        fields["body"] = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # Postgres JSONB can't store NUL characters
        fields["body"] = body.decode("utf-8", errors="replace").replace("\x00", "")
    return fields


def _jsonable(value: Any) -> Any:
    """ASGI scope values -> JSON (bytes decoded, tuples as lists, objects by name)."""
    if isinstance(value, bytes):
        return value.decode("latin-1")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return getattr(value, "__name__", None) or getattr(value, "path", None) or type(value).__name__


SCOPE_KEYS = ("type", "asgi", "http_version", "scheme", "method", "path", "raw_path", "root_path",
              "query_string", "client", "server", "path_params")


def request_fields(request: Request, started_at: datetime) -> dict[str, Any]:
    """Everything about the request that's known before the app handles it."""
    scope = request.scope
    pairs = _decode_pairs(scope.get("headers", []))
    client = scope.get("client") or (None, None)
    forwarded_for = request.headers.get("x-forwarded-for")
    return {
        "request_uuid": str(uuid.uuid4()),
        "request_started_at": started_at,
        "method": request.method,
        "path": request.url.path,
        "url": str(request.url),
        "scheme": request.url.scheme,
        "http_version": scope.get("http_version"),
        "query_string": scope.get("query_string", b"").decode("latin-1"),
        "query_params": dict(request.query_params),
        "headers": redact_dict(pairs),
        "raw_headers": redact_pairs(pairs),
        # Behind Cloudflare the client is the tunnel; the visitor's IP is in X-Forwarded-For
        "ip": forwarded_for or client[0],
        "client_host": client[0],
        "client_port": client[1],
    }


def routing_fields(request: Request) -> dict[str, Any]:
    """Filled in by the router while the app handles the request."""
    scope = request.scope
    route, endpoint = scope.get("route"), scope.get("endpoint")
    route_path = getattr(route, "path", None)
    if route_path is None and scope.get("root_path"):
        # Mounted apps (e.g. StaticFiles at /stylesheets) set root_path instead of a route
        route_path = f"{scope['root_path']}/{{path}}"
    return {
        "route": route_path,
        "endpoint": getattr(endpoint, "__name__", None),
        "path_params": scope.get("path_params") or {},
        "scope": {k: _jsonable(scope[k]) for k in SCOPE_KEYS if k in scope},
    }


def response_fields(response: Response) -> dict[str, Any]:
    pairs = [(k.lower(), v) for k, v in response.headers.items()]
    return {
        "status_code": response.status_code,
        "response_headers": redact_dict(pairs),
        "response_content_type": response.headers.get("content-type"),
    }


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def wait_for_logs() -> None:
    """Await every logging task still running (used by tests and on shutdown)."""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)


async def _write_safely(record: dict[str, Any], persist) -> None:
    try:
        await persist(record)
    except Exception:
        logger.exception("Failed to log %s %s", record.get("method"), record.get("path"))


async def capture(request: Request, call_next, persist) -> Response:
    """Middleware body: handle the request, then log it with `persist(record)` in the background.

    `persist` is an async function taking the record dict (main.py passes one that writes to
    Postgres). Any problem building the record is logged; the response is always returned.
    """
    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    try:
        record = request_fields(request, started_at)
        record.update(body_fields(await request.body(), request.headers.get("content-type")))
    except Exception:
        logger.exception("Failed to read request %s %s", request.method, request.url.path)
        return await call_next(request)

    try:
        response = await call_next(request)
    except Exception as exc:
        # The app raised: still log the request (as a 500), then let the error propagate
        record.update(routing_fields(request), status_code=500, error=f"{type(exc).__name__}: {exc}",
                      duration_ms=round((time.perf_counter() - t0) * 1000, 3))
        _spawn(_write_safely(record, persist))
        raise

    try:
        record.update(routing_fields(request))
        record.update(response_fields(response))
        record["time_to_headers_ms"] = round((time.perf_counter() - t0) * 1000, 3)
    except Exception:
        logger.exception("Failed to read response for %s %s", request.method, request.url.path)
        return response

    body_iterator = response.body_iterator

    async def counted_body():
        # Count the bytes as they're sent; log once the whole body has gone out (or the client left)
        size = 0
        try:
            async for chunk in body_iterator:
                size += len(chunk)
                yield chunk
        finally:
            record.update(response_size=size, duration_ms=round((time.perf_counter() - t0) * 1000, 3))
            _spawn(_write_safely(record, persist))

    response.body_iterator = counted_body()
    return response
