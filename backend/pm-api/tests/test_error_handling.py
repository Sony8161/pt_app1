"""Every failure, including the ones that should never happen, leaves in the same error shape and rolls nothing half-done."""

from __future__ import annotations

import logging

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import ConflictError, ForbiddenError, register_error_handlers


@pytest.fixture
def failing() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/duplicate")
    def duplicate() -> None:
        raise psycopg.errors.UniqueViolation("duplicate key value violates unique constraint")

    @app.get("/db-down")
    def db_down() -> None:
        raise psycopg.OperationalError("server closed the connection unexpectedly")

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    @app.get("/forbidden")
    def forbidden() -> None:
        raise ForbiddenError()

    @app.get("/conflict")
    def conflict() -> None:
        raise ConflictError("Already done", code="already_done", details=[{"field": "name", "message": "Already in use"}])

    return TestClient(app, raise_server_exceptions=False)


def shape(resp):
    body = resp.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "details"}
    return body["error"]


def test_a_race_the_services_missed_becomes_a_409_not_a_crash(failing, caplog):
    caplog.set_level(logging.WARNING)
    resp = failing.get("/duplicate")
    assert resp.status_code == 409 and shape(resp)["code"] == "conflict"
    assert "constraint" not in resp.text  # the database's own wording is not shown to users


def test_a_database_outage_asks_the_caller_to_retry(failing):
    resp = failing.get("/db-down")
    assert resp.status_code == 503 and shape(resp)["code"] == "database_unavailable"
    assert "retry" in shape(resp)["message"].lower()


def test_an_unexpected_error_is_a_500_that_does_not_leak_internals(failing):
    resp = failing.get("/boom")
    assert resp.status_code == 500 and shape(resp)["code"] == "internal_error"
    assert "secret internal detail" not in resp.text


def test_known_failures_keep_their_code_message_and_details(failing):
    forbidden = failing.get("/forbidden")
    assert forbidden.status_code == 403 and shape(forbidden)["code"] == "forbidden"
    conflict = failing.get("/conflict")
    assert conflict.status_code == 409
    assert shape(conflict) == {"code": "already_done", "message": "Already done", "details": [{"field": "name", "message": "Already in use"}]}


def test_an_unknown_url_and_a_wrong_method_use_the_same_shape(failing):
    assert shape(failing.get("/nope"))["code"] == "not_found"
    wrong = failing.post("/boom")
    assert wrong.status_code == 405 and shape(wrong)["code"] == "method_not_allowed"
