"""FastAPI application factory for the ACME project-tracking API."""

from __future__ import annotations

from typing import Any

import psycopg
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app import __version__
from app.config import API_PREFIX, get_settings
from app.core.errors import register_error_handlers
from app.core.observability import RequestLogMiddleware, configure_logging
from app.db import TransactionMiddleware, get_connection, register_post_migrate_hook
from app.domains.admin.router import router as admin_router
from app.domains.assignments.router import router as team_router
from app.domains.auth.router import router as auth_router
from app.domains.costs.router import router as costs_router
from app.domains.deliverables.router import router as deliverables_router
from app.domains.milestones.router import router as milestones_router
from app.domains.projects.router import router as projects_router
from app.domains.reports.router import router as reports_router
from app.domains.users.router import router as users_router
from app.seed import ensure_bootstrap_admin


class RootPathMiddleware:
    """Treat ``/api/pm-api`` as the app's mount point when the request path carries it.

    CloudFront forwards ``/api/pm-api/...`` untouched while the local proxy and direct Lambda
    URLs strip it; with ``root_path`` set (and the path left alone) routing and the OpenAPI
    docs work in both cases.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] in {"http", "websocket"} and scope.get("path", "").startswith(API_PREFIX):
            scope["root_path"] = API_PREFIX
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    """Build the application: routers, error handlers, middleware, first-admin bootstrap."""
    configure_logging()
    app = FastAPI(
        title="ACME Project Tracker API",
        version=__version__,
        description=(
            "Projects, milestones, deliverables, teams and budgets. Every Monday-Friday on a milestone is an 8-hour shift.\n\n"
            "Sign in with `POST /auth/login`, then send `Authorization: Bearer <token>`. "
            "Nothing is ever deleted: removing something archives it."
        ),
    )
    register_error_handlers(app)

    for router in (
        auth_router, users_router, projects_router, milestones_router, deliverables_router, team_router,
        costs_router, reports_router, admin_router,
    ):
        app.include_router(router)

    @app.get("/", include_in_schema=False)
    @app.get("/health", tags=["health"])
    def health() -> JSONResponse:
        """Liveness plus a database check. Returns 503 when the database cannot be reached."""
        body: dict[str, Any] = {"service": "pm-api", "version": __version__, "env": get_settings().app_env}
        try:
            get_connection().execute("SELECT 1").fetchone()
            body.update(status="ok", database="ok")
            return JSONResponse(body)
        except psycopg.Error:
            body.update(status="degraded", database="error")
            return JSONResponse(body, status_code=503)

    # Middleware added last runs first: the root path is fixed before the transaction starts.
    app.add_middleware(TransactionMiddleware)
    app.add_middleware(RootPathMiddleware)
    app.add_middleware(RequestLogMiddleware)  # outermost: times everything, including the commit
    register_post_migrate_hook(ensure_bootstrap_admin)
    return app


app = create_app()
