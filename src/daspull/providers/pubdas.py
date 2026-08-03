"""Dependency-light access to datasets hosted by PubDAS.

PubDAS is exposed through a Globus collection.  This module talks to the
Globus Transfer and collection HTTPS APIs using ``requests`` directly.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from pathlib import Path
from urllib.parse import quote

import requests

from ..catalog import (
    RemoteFile,
    directory_path,
    file_path,
    local_relative_path,
    resolve_literal_path,
)
from ..download import DownloadRedirectError, download

TRANSFER_API_URL = "https://transfer.api.globus.org/v0.10"
# Every PubDAS dataset config names this collection.
PUBDAS_COLLECTION_ID = "706e304c-5def-11ec-9b5c-f9dfb1abb183"


class PubDASError(RuntimeError):
    """Base error for PubDAS access."""


class PubDASAuthenticationError(PubDASError):
    """Raised when Globus credentials are missing or insufficient."""


class PubDASHTTPUnavailableError(PubDASError):
    """Raised when a collection does not expose file downloads over HTTPS."""


class PubDASClient:
    """Browse and download a PubDAS collection through plain HTTPS."""

    def __init__(
        self,
        transfer_token: str,
        *,
        https_token: str | None = None,
        collection_id: str = PUBDAS_COLLECTION_ID,
        https_base_url: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        if not transfer_token:
            raise ValueError("A Globus Transfer API token is required")
        self.transfer_token = transfer_token
        self.https_token = https_token
        self.collection_id = collection_id
        self._https_base_url = https_base_url
        self.session = session or requests.Session()

    def collection_https_url(self) -> str:
        """Return the collection's HTTPS data URL, discovering it if needed."""
        if self._https_base_url:
            return self._https_base_url.rstrip("/")

        document = self._transfer_get(f"/endpoint/{self.collection_id}")
        https_server = document.get("https_server")
        if not https_server:
            raise PubDASHTTPUnavailableError(
                "The PubDAS collection does not currently advertise HTTPS "
                "downloads. Its administrator must enable Globus HTTPS access."
            )
        self._https_base_url = str(https_server)
        return self._https_base_url.rstrip("/")

    def list_files(self, root: str) -> list[RemoteFile]:
        """Recursively list files below *root* in the PubDAS collection."""
        return sorted(self.iter_files(root), key=lambda item: item.path)

    def iter_files(
        self,
        root: str,
        *,
        descend: Callable[[str], bool] | None = None,
    ) -> Iterator[RemoteFile]:
        """Yield files while recursively traversing *root*.

        Unlike :meth:`list_files`, this lets callers display matches and stop
        at a limit without waiting for the entire dataset tree.
        """
        root = directory_path(root)
        pending = deque([root])
        visited: set[str] = set()

        while pending:
            directory = pending.popleft()
            if directory in visited:
                continue
            visited.add(directory)
            listing = self._transfer_get(
                f"/operation/endpoint/{self.collection_id}/ls",
                params={"path": directory, "show_hidden": "1"},
            )

            for item in listing.get("DATA", []):
                name = str(item.get("name", ""))
                if not name or "/" in name or name in {".", ".."}:
                    continue
                path = f"{directory}{name}"
                item_type = item.get("type")
                if item_type == "dir":
                    child = directory_path(path)
                    if descend is None or descend(child):
                        pending.append(child)
                elif item_type == "file":
                    yield RemoteFile(
                        path=path,
                        size=int(item.get("size") or 0),
                        last_modified=item.get("last_modified"),
                        checksum=item.get("checksum"),
                    )

    def stat_file(
        self,
        path: str,
        *,
        root: str,
    ) -> RemoteFile:
        """Resolve one exact dataset path without scanning the catalog."""
        remote_path = resolve_literal_path(path, root)
        document = self._transfer_get(
            f"/operation/endpoint/{self.collection_id}/stat",
            params={"path": remote_path},
        )
        if document.get("type") != "file":
            raise PubDASError(f"Not a file: {remote_path}")
        return RemoteFile(
            path=remote_path,
            size=int(document.get("size") or 0),
            last_modified=document.get("last_modified"),
            checksum=document.get("checksum"),
        )

    def download_file(
        self,
        remote: RemoteFile,
        dest: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Download one catalogued file, preserving resumable partial data."""
        remote_path = file_path(remote.path)
        url = (
            f"{self.collection_https_url()}/{quote(remote_path.lstrip('/'), safe='/')}"
        )
        headers = {"X-Requested-With": "XMLHttpRequest"}
        if self.https_token:
            headers["Authorization"] = f"Bearer {self.https_token}"

        try:
            return download(
                url,
                dest,
                overwrite=overwrite,
                expected_size=remote.size or None,
                checksum=remote.checksum,
                headers=headers,
                session=self.session,
                allow_redirects=False,
            )
        except DownloadRedirectError as exc:
            raise PubDASAuthenticationError(
                "The PubDAS HTTPS server requires a collection HTTPS token"
            ) from exc
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {401, 403}:
                raise PubDASAuthenticationError(
                    "The PubDAS HTTPS token is missing, expired, or lacks "
                    "permission for this file; run `daspull login --globus` "
                    "again"
                ) from exc
            raise

    def download_files(
        self,
        files: list[RemoteFile],
        dest_dir: str | Path,
        *,
        root: str,
        overwrite: bool = False,
    ) -> list[Path]:
        """Download files while preserving their paths relative to *root*."""
        root = directory_path(root)
        destination = Path(dest_dir)
        results: list[Path] = []
        for remote in files:
            relative = local_relative_path(remote.path, root)
            results.append(
                self.download_file(remote, destination / relative, overwrite=overwrite)
            )
        return results

    def _transfer_get(self, path: str, *, params: dict[str, str] | None = None) -> dict:
        response = self.session.get(
            f"{TRANSFER_API_URL}{path}",
            params=params,
            headers={"Authorization": f"Bearer {self.transfer_token}"},
            timeout=(10, 120),
        )
        if response.status_code in {401, 403}:
            try:
                detail = response.json().get("message", response.text)
            except requests.JSONDecodeError:
                detail = response.text
            raise PubDASAuthenticationError(str(detail).strip())
        response.raise_for_status()
        return response.json()
