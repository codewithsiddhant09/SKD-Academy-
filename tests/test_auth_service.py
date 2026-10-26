from __future__ import annotations

from unittest.mock import Mock

import httpx
import pytest

from app.services.auth_service import AuthService


def test_login_posts_credentials_and_returns_token_without_logging_it(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "error": False,
        "results": {"user": {"_id": "user-1"}, "token": "secret-token"},
    }
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.return_value = response
    monkeypatch.setattr("app.services.auth_service.httpx.Client", lambda **_: client)

    result = AuthService().login(
        {"email": "person@example.test", "password": "secret"},
        {"x-auth-language": "English", "x-user-type": "User"},
    )

    assert result == {"token": "secret-token", "user_id": "user-1"}
    assert client.post.call_args.args[0].endswith("/login")
    assert client.post.call_args.kwargs["json"]["password"] == "secret"
    assert client.post.call_args.kwargs["headers"] == {
        "x-auth-language": "English", "x-user-type": "User",
    }


def test_login_rejects_response_without_token(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"error": False, "results": {"user": {"_id": "user-1"}}}
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.return_value = response
    monkeypatch.setattr("app.services.auth_service.httpx.Client", lambda **_: client)

    with pytest.raises(RuntimeError, match="authentication token"):
        AuthService().login({"email": "person@example.test", "password": "secret"}, {})


def test_login_maps_bad_credentials_without_exposing_upstream_body(monkeypatch):
    response = Mock()
    response.status_code = 401
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad credentials", request=Mock(), response=response
    )
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.return_value = response
    monkeypatch.setattr("app.services.auth_service.httpx.Client", lambda **_: client)

    with pytest.raises(RuntimeError, match="rejected the login credentials"):
        AuthService().login({"email": "person@example.test", "password": "secret"}, {})
