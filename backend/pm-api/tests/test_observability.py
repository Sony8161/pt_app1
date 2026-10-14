"""Every request leaves one access-log line and an X-Request-Id, and secrets stay out of the log."""

from __future__ import annotations

import json
import logging

import pytest

pytestmark = pytest.mark.integration


def access_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "pm_api.access"]


def test_each_request_is_logged_with_status_time_and_an_id(api, caplog):
    caplog.set_level(logging.INFO, logger="pm_api.access")
    missing = api.client.get("/projects/00000000-0000-0000-0000-000000000000", headers={**api.admin.headers, "X-Request-Id": "trace-123"})
    assert missing.status_code == 404 and missing.headers["x-request-id"] == "trace-123"
    line = access_lines(caplog)[-1]
    assert line["method"] == "GET" and line["status"] == 404 and line["request_id"] == "trace-123"
    assert line["path"].endswith("00000000-0000-0000-0000-000000000000") and isinstance(line["ms"], int)


def test_a_request_without_an_id_gets_one(api):
    resp = api.client.get("/health")
    assert len(resp.headers["x-request-id"]) >= 16


def test_tokens_and_query_text_are_never_logged(api, caplog):
    caplog.set_level(logging.INFO, logger="pm_api.access")
    api.client.get("/projects?q=secret-search-text", headers=api.admin.headers)
    token = api.admin.headers["Authorization"].split()[1]
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert token not in logged and "secret-search-text" not in logged
