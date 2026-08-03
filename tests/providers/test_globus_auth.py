import base64
import hashlib
import json
import os
import stat
import time
from urllib.parse import parse_qs, urlparse

import pytest

from daspull.providers.globus_auth import (
    GLOBUS_CLIENT_ID,
    GLOBUS_NATIVE_REDIRECT_URI,
    PUBDAS_HTTPS_SCOPE,
    GlobusAuthError,
    NativeLoginFlow,
    TokenStore,
    exchange_authorization_code,
    start_native_login,
)


class JsonResponse:
    def __init__(self, payload, *, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload


class PostSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_native_login_uses_registered_client_and_pkce():
    flow = start_native_login()
    query = parse_qs(urlparse(flow.authorization_url).query)
    expected_challenge = (
        base64.urlsafe_b64encode(
            hashlib.sha256(flow.code_verifier.encode("ascii")).digest()
        )
        .rstrip(b"=")
        .decode("ascii")
    )

    assert query["client_id"] == [GLOBUS_CLIENT_ID]
    assert query["redirect_uri"] == [GLOBUS_NATIVE_REDIRECT_URI]
    assert query["response_type"] == ["code"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [expected_challenge]
    assert "offline_access" in query["scope"][0].split()
    assert PUBDAS_HTTPS_SCOPE in query["scope"][0].split()


def test_exchange_accepts_redirect_url_and_checks_state():
    flow = NativeLoginFlow("https://auth.example", "verifier", "expected")
    session = PostSession(
        [
            JsonResponse(
                {
                    "resource_server": "transfer.api.globus.org",
                    "access_token": "access",
                }
            )
        ]
    )

    response = exchange_authorization_code(
        flow,
        "https://auth.globus.org/v2/web/auth-code"
        "?code=authorization-code&state=expected",
        session=session,
    )

    assert response["access_token"] == "access"
    form = session.calls[0][1]["data"]
    assert form["client_id"] == GLOBUS_CLIENT_ID
    assert form["code"] == "authorization-code"
    assert form["code_verifier"] == "verifier"

    with pytest.raises(GlobusAuthError, match="state did not match"):
        exchange_authorization_code(
            flow,
            "https://auth.globus.org/v2/web/auth-code?code=x&state=wrong",
            session=session,
        )


def test_token_store_saves_private_file_and_returns_access_token(tmp_path):
    path = tmp_path / "config" / "tokens.json"
    store = TokenStore(path)
    store.save_response(
        {
            "resource_server": "transfer.api.globus.org",
            "access_token": "transfer-access",
            "refresh_token": "transfer-refresh",
            "expires_in": 3600,
        }
    )

    assert store.access_token() == "transfer-access"
    document = json.loads(path.read_text())
    assert document["client_id"] == GLOBUS_CLIENT_ID
    if os.name == "posix":
        # NTFS has no equivalent of Unix permission bits, so os.chmod's
        # effect (and this assertion) is only meaningful on POSIX.
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_token_store_refreshes_expired_token(tmp_path):
    path = tmp_path / "tokens.json"
    store = TokenStore(path)
    store.save_response(
        {
            "resource_server": "transfer.api.globus.org",
            "access_token": "expired",
            "refresh_token": "refresh-me",
            "expires_at_seconds": int(time.time()) - 1,
        }
    )
    session = PostSession(
        [
            JsonResponse(
                {
                    "resource_server": "transfer.api.globus.org",
                    "access_token": "fresh",
                    "expires_in": 3600,
                }
            )
        ]
    )

    assert TokenStore(path, session=session).access_token() == "fresh"
    form = session.calls[0][1]["data"]
    assert form == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-me",
        "client_id": GLOBUS_CLIENT_ID,
    }
    saved = json.loads(path.read_text())["tokens"]["transfer.api.globus.org"]
    assert saved["refresh_token"] == "refresh-me"


def test_token_store_selects_collection_token_by_scope(tmp_path):
    path = tmp_path / "tokens.json"
    store = TokenStore(path)
    store.save_response(
        {
            "resource_server": "transfer.api.globus.org",
            "access_token": "transfer-access",
            "scope": "urn:globus:auth:scope:transfer.api.globus.org:all",
            "other_tokens": [
                {
                    "resource_server": "pubdas.example",
                    "access_token": "https-access",
                    "scope": PUBDAS_HTTPS_SCOPE,
                }
            ],
        }
    )

    assert store.access_token_for_scope(PUBDAS_HTTPS_SCOPE) == "https-access"
