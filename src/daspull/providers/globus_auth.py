"""Globus native-app authentication for DASPull."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import requests

GLOBUS_CLIENT_ID = "47061e53-cf57-469a-9c0a-d67a135f91f9"
GLOBUS_AUTHORIZE_URL = "https://auth.globus.org/v2/oauth2/authorize"
GLOBUS_TOKEN_URL = "https://auth.globus.org/v2/oauth2/token"
GLOBUS_NATIVE_REDIRECT_URI = "https://auth.globus.org/v2/web/auth-code"
TRANSFER_RESOURCE_SERVER = "transfer.api.globus.org"
TRANSFER_SCOPE = "urn:globus:auth:scope:transfer.api.globus.org:all"
PUBDAS_HTTPS_SCOPE = (
    "https://auth.globus.org/scopes/706e304c-5def-11ec-9b5c-f9dfb1abb183/https"
)
DEFAULT_SCOPES = (TRANSFER_SCOPE, PUBDAS_HTTPS_SCOPE, "offline_access")


class GlobusAuthError(RuntimeError):
    """Raised when Globus authentication or local token handling fails."""


@dataclass(frozen=True)
class NativeLoginFlow:
    """Ephemeral values required to complete one PKCE login."""

    authorization_url: str
    code_verifier: str
    state: str


def start_native_login() -> NativeLoginFlow:
    """Create a Globus authorization URL for DASPull's registered native app."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    state = secrets.token_urlsafe(24)
    query = urlencode(
        {
            "client_id": GLOBUS_CLIENT_ID,
            "redirect_uri": GLOBUS_NATIVE_REDIRECT_URI,
            "scope": " ".join(DEFAULT_SCOPES),
            "state": state,
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return NativeLoginFlow(
        authorization_url=f"{GLOBUS_AUTHORIZE_URL}?{query}",
        code_verifier=code_verifier,
        state=state,
    )


def exchange_authorization_code(
    flow: NativeLoginFlow,
    authorization_response: str,
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Exchange a pasted authorization code or redirect URL for tokens."""
    code = _authorization_code(authorization_response, expected_state=flow.state)
    return _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": GLOBUS_CLIENT_ID,
            "redirect_uri": GLOBUS_NATIVE_REDIRECT_URI,
            "code_verifier": flow.code_verifier,
        },
        session=session,
    )


class TokenStore:
    """Store and refresh Globus tokens in a user-private local JSON file."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else _default_token_path()
        self.session = session

    def save_response(
        self,
        response: dict[str, Any],
        *,
        previous_refresh_token: str | None = None,
        required_resource_server: str = TRANSFER_RESOURCE_SERVER,
    ) -> None:
        """Merge a Globus multi-resource token response into the store."""
        document = self._load()
        tokens = document.setdefault("tokens", {})
        updated_resources: set[str] = set()
        for token in _token_documents(response):
            resource_server = token.get("resource_server")
            access_token = token.get("access_token")
            if not isinstance(resource_server, str) or not isinstance(
                access_token, str
            ):
                continue
            saved = dict(token)
            if "expires_at_seconds" not in saved and "expires_in" in saved:
                saved["expires_at_seconds"] = int(time.time()) + int(
                    saved["expires_in"]
                )
            if not saved.get("refresh_token") and previous_refresh_token:
                saved["refresh_token"] = previous_refresh_token
            tokens[resource_server] = saved
            updated_resources.add(resource_server)

        if required_resource_server not in updated_resources:
            raise GlobusAuthError(
                f"Globus returned no access token for {required_resource_server}"
            )
        document["version"] = 1
        document["client_id"] = GLOBUS_CLIENT_ID
        self._write(document)

    def access_token(self, resource_server: str = TRANSFER_RESOURCE_SERVER) -> str:
        """Return a valid access token, refreshing it when close to expiry."""
        document = self._load()
        token = document.get("tokens", {}).get(resource_server)
        if not isinstance(token, dict) or not token.get("access_token"):
            raise GlobusAuthError(
                "Not logged in to Globus; run `daspull login --globus` first"
            )

        expires_at = token.get("expires_at_seconds")
        if expires_at is not None and int(expires_at) <= int(time.time()) + 60:
            refresh_token = token.get("refresh_token")
            if not refresh_token:
                raise GlobusAuthError(
                    "The Globus access token has expired; run "
                    "`daspull login --globus` again"
                )
            response = _token_request(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": GLOBUS_CLIENT_ID,
                },
                session=self.session,
            )
            self.save_response(
                response,
                previous_refresh_token=str(refresh_token),
                required_resource_server=resource_server,
            )
            document = self._load()
            token = document["tokens"].get(resource_server)
            if not isinstance(token, dict) or not token.get("access_token"):
                raise GlobusAuthError(
                    f"Globus did not refresh the token for {resource_server}"
                )
        return str(token["access_token"])

    def access_token_for_scope(self, required_scope: str) -> str:
        """Return a valid token whose granted scopes include *required_scope*."""
        document = self._load()
        tokens = document.get("tokens", {})
        for resource_server, token in tokens.items():
            if not isinstance(token, dict):
                continue
            scopes = str(token.get("scope", "")).split()
            if required_scope in scopes:
                return self.access_token(str(resource_server))
        raise GlobusAuthError(
            "The Globus login does not include PubDAS HTTPS access; "
            "run `daspull login --globus` again"
        )

    def clear(self) -> bool:
        """Remove locally stored tokens and return whether a file existed."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        return True

    def _load(self) -> dict[str, Any]:
        try:
            with self.path.open(encoding="utf-8") as handle:
                document = json.load(handle)
        except FileNotFoundError:
            return {"version": 1, "client_id": GLOBUS_CLIENT_ID, "tokens": {}}
        except (OSError, json.JSONDecodeError) as exc:
            raise GlobusAuthError(
                f"Could not read the token store at {self.path}: {exc}"
            ) from exc
        if not isinstance(document, dict):
            raise GlobusAuthError(f"Invalid token store at {self.path}")
        if document.get("client_id") not in {None, GLOBUS_CLIENT_ID}:
            raise GlobusAuthError(
                "The stored tokens belong to a different Globus client; "
                "run `daspull logout --globus` and then "
                "`daspull login --globus`"
            )
        return document

    def _write(self, document: dict[str, Any]) -> None:
        try:
            parent_existed = self.path.parent.exists()
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if not parent_existed:
                self.path.parent.chmod(0o700)
            temporary = self.path.with_name(
                f".{self.path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
            )
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    json.dump(document, handle, indent=2)
                    handle.write("\n")
                temporary.replace(self.path)
                self.path.chmod(0o600)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise GlobusAuthError(
                f"Could not write the token store at {self.path}: {exc}"
            ) from exc


def _default_token_path() -> Path:
    override = os.environ.get("DASPULL_TOKEN_FILE")
    if override:
        return Path(override).expanduser()
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "daspull" / "tokens.json"


def _authorization_code(value: str, *, expected_state: str) -> str:
    value = value.strip()
    if not value:
        raise GlobusAuthError("No authorization code was provided")
    if "://" not in value:
        return value

    query = parse_qs(urlparse(value).query)
    returned_state = query.get("state", [None])[0]
    if returned_state != expected_state:
        raise GlobusAuthError("The OAuth state did not match; restart the login")
    code = query.get("code", [None])[0]
    if not code:
        error = query.get("error_description", query.get("error", [""]))[0]
        raise GlobusAuthError(error or "The redirect URL contains no code")
    return code


def _token_request(
    form: dict[str, str],
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    requester = session or requests.Session()
    try:
        response = requester.post(
            GLOBUS_TOKEN_URL,
            data=form,
            timeout=(10, 60),
        )
    except requests.RequestException as exc:
        raise GlobusAuthError(f"Could not contact Globus Auth: {exc}") from exc

    try:
        payload = response.json()
    except requests.JSONDecodeError as exc:
        raise GlobusAuthError(
            f"Globus Auth returned HTTP {response.status_code} without JSON"
        ) from exc
    if response.status_code >= 400:
        detail = payload.get("error_description") or payload.get("error")
        raise GlobusAuthError(str(detail or f"HTTP {response.status_code}"))
    if not isinstance(payload, dict):
        raise GlobusAuthError("Globus Auth returned an invalid token response")
    return payload


def _token_documents(response: dict[str, Any]) -> list[dict[str, Any]]:
    primary = {key: value for key, value in response.items() if key != "other_tokens"}
    documents = [primary]
    other = response.get("other_tokens", [])
    if isinstance(other, list):
        documents.extend(item for item in other if isinstance(item, dict))
    return documents
