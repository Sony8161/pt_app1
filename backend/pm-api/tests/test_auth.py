"""Login, first-login password change and token revocation."""

from __future__ import annotations

import pytest

from tests.conftest import BOOTSTRAP_PASSWORD, BOOTSTRAP_USER, GOOD_PASSWORD

pytestmark = pytest.mark.integration


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_bootstrap_admin_must_change_password_before_anything_else(client):
    login = client.post("/auth/login", json={"username": BOOTSTRAP_USER, "password": BOOTSTRAP_PASSWORD})
    assert login.status_code == 200
    body = login.json()
    assert body["user"]["role"] == "admin" and body["user"]["must_change_password"] is True
    headers = bearer(body["access_token"])

    blocked = client.get("/projects", headers=headers)
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "password_change_required"
    assert client.get("/auth/me", headers=headers).status_code == 200  # still allowed


def test_wrong_password_and_unknown_user_look_the_same(client):
    wrong = client.post("/auth/login", json={"username": BOOTSTRAP_USER, "password": "nope"})
    unknown = client.post("/auth/login", json={"username": "nobody", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_is_not_case_sensitive_on_username(client):
    assert client.post("/auth/login", json={"username": "ADMIN1", "password": BOOTSTRAP_PASSWORD}).status_code == 200


def test_change_password_rules(client):
    token = client.post("/auth/login", json={"username": BOOTSTRAP_USER, "password": BOOTSTRAP_PASSWORD}).json()["access_token"]
    h = bearer(token)

    weak = client.post("/auth/change-password", json={"current_password": BOOTSTRAP_PASSWORD, "new_password": "weak"}, headers=h)
    assert weak.status_code == 400 and weak.json()["error"]["details"][0]["field"] == "new_password"

    wrong = client.post("/auth/change-password", json={"current_password": "wrong", "new_password": GOOD_PASSWORD}, headers=h)
    assert wrong.status_code == 400 and wrong.json()["error"]["details"][0]["field"] == "current_password"

    same = client.post("/auth/change-password", json={"current_password": BOOTSTRAP_PASSWORD, "new_password": BOOTSTRAP_PASSWORD}, headers=h)
    assert same.status_code == 400


def test_password_change_revokes_old_tokens(client):
    old = client.post("/auth/login", json={"username": BOOTSTRAP_USER, "password": BOOTSTRAP_PASSWORD}).json()["access_token"]
    changed = client.post(
        "/auth/change-password", json={"current_password": BOOTSTRAP_PASSWORD, "new_password": GOOD_PASSWORD}, headers=bearer(old)
    )
    assert changed.status_code == 200
    new = changed.json()["access_token"]

    revoked = client.get("/auth/me", headers=bearer(old))
    assert revoked.status_code == 401 and revoked.json()["error"]["code"] == "token_revoked"
    assert client.get("/projects", headers=bearer(new)).status_code == 200
    assert client.post("/auth/login", json={"username": BOOTSTRAP_USER, "password": BOOTSTRAP_PASSWORD}).status_code == 401


def test_refresh_issues_a_new_working_token(api):
    resp = api.client.post("/auth/refresh", headers=api.admin.headers)
    assert resp.status_code == 200
    assert api.client.get("/auth/me", headers=bearer(resp.json()["access_token"])).status_code == 200


@pytest.mark.parametrize("header", [None, "Bearer", "Bearer not.a.jwt", "Basic abc"])
def test_missing_or_bad_tokens_are_401(client, header):
    headers = {"Authorization": header} if header else {}
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 401 and resp.json()["error"]["code"] in {"unauthenticated", "token_invalid"}


def test_archived_user_cannot_log_in_or_use_old_tokens(api):
    manager = api.user("manager")
    assert api.client.post(f"/users/{manager.id}/archive", headers=api.admin.headers).status_code == 200
    assert api.client.get("/auth/me", headers=manager.headers).status_code == 401
    login = api.client.post("/auth/login", json={"username": manager.username, "password": GOOD_PASSWORD})
    assert login.status_code == 401


def test_validation_errors_use_the_envelope(client):
    resp = client.post("/auth/login", json={"username": ""})
    assert resp.status_code == 400
    error = resp.json()["error"]
    assert error["code"] == "validation_error" and {d["field"] for d in error["details"]} == {"username", "password"}
