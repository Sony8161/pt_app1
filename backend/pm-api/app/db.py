"""
PostgreSQL connectivity and schema migrations.

One connection is kept per Lambda container and reused across invocations
(the same pattern as ``backend/_examples/python-service``). Each HTTP request
runs inside a single transaction that :class:`TransactionMiddleware` commits
when the response is successful and rolls back otherwise.

Migrations are plain SQL files in ``app/migrations`` applied in filename order
and recorded in ``schema_migrations``. They run once per container on the
first request, serialised across containers with a PostgreSQL advisory lock.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

from app.config import get_settings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Arbitrary application-wide lock id so concurrent cold starts migrate one at a time.
MIGRATION_LOCK_ID = 727_001

_conn: psycopg.Connection[Any] | None = None
_migrated = False
# Hooks executed once after migrations (e.g. seeding the bootstrap admin).
_post_migrate_hooks: list[Callable[[psycopg.Connection[Any]], None]] = []


def connect(conninfo: str, *, attempts: int = 2, delay_seconds: float = 3.0) -> psycopg.Connection[Any]:
    """Open a connection, retrying once so a brief network blip does not fail the request.

    Total wait stays well under CloudFront's 60s origin timeout so an outage surfaces as a
    JSON 503 rather than a CloudFront 504 page.
    """
    last_error: psycopg.OperationalError | None = None
    for attempt in range(1, attempts + 1):
        try:
            # Session time zone UTC: timestamptz values must reach the API as UTC ("...Z").
            return psycopg.connect(conninfo, row_factory=dict_row, options="-c timezone=UTC")
        except psycopg.OperationalError as exc:
            last_error = exc
            logger.warning("PostgreSQL connection attempt %d/%d failed: %s", attempt, attempts, exc)
            if attempt < attempts:
                time.sleep(delay_seconds)
    if last_error is None:  # pragma: no cover - attempts is always >= 1
        raise psycopg.OperationalError("PostgreSQL connection failed")
    raise last_error


def get_connection() -> psycopg.Connection[Any]:
    """Return the shared connection, (re)connecting if it is missing, broken or stale."""
    global _conn
    if _conn is not None and not _conn.closed and not _conn.broken:
        try:
            # Cheap liveness probe: a server-side disconnect (e.g. Aurora scaling) only
            # shows up when a statement is executed, so detect it here rather than mid-request.
            if _conn.info.transaction_status == TransactionStatus.IDLE:
                _conn.execute("SELECT 1").fetchone()
            return _conn
        except psycopg.OperationalError:
            logger.warning("Shared PostgreSQL connection is stale; reconnecting")
            reset_connection()
    _conn = connect(get_settings().pg_conninfo)
    return _conn


def reset_connection() -> None:
    """Drop the shared connection so the next request reconnects."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except psycopg.Error:  # pragma: no cover - best effort
            pass
    _conn = None


def finalize_transaction(*, ok: bool) -> bool:
    """Commit (``ok``) or roll back any open transaction on the shared connection.

    Returns ``False`` when the commit itself failed, so the caller can turn an
    otherwise successful response into an error.
    """
    conn = _conn
    if conn is None or conn.closed:
        return True
    try:
        status = conn.info.transaction_status
        if status == TransactionStatus.IDLE:
            return True
        if status == TransactionStatus.INERROR:
            # A statement failed and nobody rolled back: COMMIT would silently become a
            # ROLLBACK on the server, so never let a 2xx through in this state.
            conn.rollback()
            if ok:
                logger.error("Transaction was in an error state at commit time; rolled back")
            return not ok
        if ok:
            conn.commit()
        else:
            conn.rollback()
        return True
    except psycopg.Error:
        logger.exception("Failed to %s transaction", "commit" if ok else "roll back")
        reset_connection()
        return False


def applied_versions(conn: psycopg.Connection[Any]) -> set[str]:
    """Versions already recorded in ``schema_migrations``."""
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] for row in rows}


def run_migrations(conn: psycopg.Connection[Any], migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending ``*.sql`` migrations in order; returns the versions applied."""
    with conn.transaction():
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    text        PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )

    applied_now: list[str] = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,))
        already = applied_versions(conn)
        for path in sorted(migrations_dir.glob("*.sql")):
            version = path.stem
            if version in already:
                continue
            logger.info("Applying migration %s", version)
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            applied_now.append(version)
    return applied_now


def register_post_migrate_hook(hook: Callable[[psycopg.Connection[Any]], None]) -> None:
    """Register a callable to run after migrations on first use (idempotent hooks only)."""
    _post_migrate_hooks.append(hook)


def ensure_migrated(conn: psycopg.Connection[Any]) -> None:
    """Run migrations and post-migrate hooks once per process when AUTO_MIGRATE is on."""
    global _migrated
    if _migrated or not get_settings().auto_migrate:
        return
    # Close the transaction the liveness probe opened. Without this the migrations would
    # become a savepoint inside the request transaction, and a first request that ends in
    # a 4xx would roll the whole schema back while _migrated is already True.
    conn.commit()
    applied = run_migrations(conn)
    if applied:
        logger.info("Applied migrations: %s", ", ".join(applied))
    for hook in _post_migrate_hooks:
        with conn.transaction():
            hook(conn)
    _migrated = True


def reset_migration_state() -> None:
    """Forget that migrations ran (used by tests that rebuild the schema)."""
    global _migrated
    _migrated = False


class TransactionMiddleware:
    """ASGI middleware giving every HTTP request transactional semantics.

    The response is held back until the transaction is finalised so a client
    never sees a 2xx for work that failed to commit.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        pending_start: dict[str, Any] | None = None
        response_status = 500

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal pending_start, response_status
            if message["type"] == "http.response.start":
                pending_start = message
                response_status = int(message["status"])
                return
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                committed = finalize_transaction(ok=response_status < 400)
                if not committed and pending_start is not None:
                    pending_start, message = _commit_failed_response()
            if pending_start is not None:
                await send(pending_start)
                pending_start = None
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException:
            finalize_transaction(ok=False)
            raise


def _commit_failed_response() -> tuple[dict[str, Any], dict[str, Any]]:
    """Replacement 503 response used when the final commit fails."""
    body = (
        b'{"error":{"code":"database_unavailable",'
        b'"message":"The change could not be saved. Please retry.","details":[]}}'
    )
    start = {
        "type": "http.response.start",
        "status": 503,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    }
    return start, {"type": "http.response.body", "body": body, "more_body": False}
