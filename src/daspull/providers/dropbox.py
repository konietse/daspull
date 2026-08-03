"""Dependency-light access to a dataset published as a public Dropbox folder."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from ..catalog import (
    RemoteFile,
    directory_path,
    local_relative_path,
    relative_to_root,
    resolve_literal_path,
)
from ..download import download

DEFAULT_TIMEOUT = (10, 120)
ENTRIES_URL = "https://www.dropbox.com/list_shared_link_folder_entries"
#: Guards against a voucher that never advances turning paging into a spin.
MAX_PAGES_PER_DIRECTORY = 1000


class DropboxError(RuntimeError):
    """Raised when a Dropbox-hosted folder cannot be listed or read."""


class _Entry:
    """One listed child of a folder level: a file's metadata, or a subfolder."""

    __slots__ = ("href", "is_dir", "remote")

    def __init__(self, remote: RemoteFile, href: str, is_dir: bool) -> None:
        self.remote = remote
        self.href = href
        self.is_dir = is_dir


class DropboxClient:
    """Browse and download a dataset published as a public Dropbox folder."""

    def __init__(
        self,
        share_url: str,
        dataset_root: str,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.share_url = share_url
        self.dataset_root = directory_path(dataset_root)
        self.session = session or requests.Session()
        self.link_key, self.secure_hash, self.rlkey = _parse_share_url(share_url)
        self._csrf_token: str | None = None
        self._listings: dict[str, list[_Entry]] = {}

    def list_files(self, root: str) -> list[RemoteFile]:
        """Recursively list every file below *root* in the shared folder."""
        return sorted(self.iter_files(root), key=lambda item: item.path)

    def iter_files(
        self,
        root: str,
        *,
        descend: Callable[[str], bool] | None = None,
    ) -> Iterator[RemoteFile]:
        """Yield files while recursively traversing *root*.

        Each folder level is one paginated listing request, so *descend*
        genuinely prunes subtrees instead of only filtering an already-fetched
        catalog.
        """
        pending = deque([directory_path(root)])
        visited: set[str] = set()

        while pending:
            virtual_dir = pending.popleft()
            if virtual_dir in visited:
                continue
            visited.add(virtual_dir)
            for entry in self._directory(virtual_dir):
                if entry.is_dir:
                    child = directory_path(entry.remote.path)
                    if descend is None or descend(child):
                        pending.append(child)
                else:
                    yield entry.remote

    def stat_file(self, path: str, *, root: str) -> RemoteFile:
        """Resolve one exact dataset path by listing just its parent folder."""
        remote_path = resolve_literal_path(path, root)
        entry = self._entry(remote_path)
        return entry.remote

    def download_file(
        self,
        remote: RemoteFile,
        dest: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Download one catalogued file, resuming any partial local data."""
        href = self._entry(remote.path).href
        return download(
            _with_query_param(href, "dl", "1"),
            dest,
            overwrite=overwrite,
            expected_size=remote.size or None,
            session=self.session,
        )

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

    def _entry(self, remote_path: str) -> _Entry:
        """Return the listed entry for one exact file path."""
        parent = directory_path(str(PurePosixPath(remote_path).parent))
        for entry in self._directory(parent):
            if not entry.is_dir and entry.remote.path == remote_path:
                return entry
        raise DropboxError(f"Not a file in this shared folder: {remote_path}")

    def _directory(self, virtual_dir: str) -> list[_Entry]:
        """Return one folder level's children, listing it once and caching it."""
        virtual_dir = directory_path(virtual_dir)
        cached = self._listings.get(virtual_dir)
        if cached is not None:
            return cached

        entries: list[_Entry] = []
        voucher: str | None = None
        for _ in range(MAX_PAGES_PER_DIRECTORY):
            document = self._request_entries(virtual_dir, voucher)
            for item in document.get("entries", ()):
                entries.append(self._entry_from(virtual_dir, item))
            if not document.get("has_more_entries"):
                break
            voucher = document.get("next_request_voucher")
            if not voucher:
                raise DropboxError(
                    f"Dropbox reported more entries below {virtual_dir} but "
                    "sent no pagination voucher"
                )
        else:
            raise DropboxError(
                f"Dropbox paging below {virtual_dir} did not finish within "
                f"{MAX_PAGES_PER_DIRECTORY} pages"
            )

        self._listings[virtual_dir] = entries
        return entries

    def _entry_from(self, virtual_dir: str, item: dict) -> _Entry:
        """Turn one raw listing entry into an :class:`_Entry`."""
        filename = item.get("filename")
        href = item.get("href")
        if not filename or not href:
            raise DropboxError(
                f"Unexpected Dropbox listing entry below {virtual_dir}: {item!r}"
            )
        is_dir = bool(item.get("is_dir"))
        remote = RemoteFile(
            path=f"{virtual_dir}{filename}",
            size=0 if is_dir else int(item.get("bytes") or 0),
            last_modified=_modified_date(item.get("ts")),
        )
        return _Entry(remote, href, is_dir)

    def _request_entries(self, virtual_dir: str, voucher: str | None) -> dict:
        """Ask for one page of *virtual_dir*'s entries, refreshing a stale token."""
        response = self._post_entries(virtual_dir, voucher)
        if response.status_code == 403:
            # A 403 is exactly what a missing or expired CSRF token looks like;
            # drop it so one retry picks a fresh one up from the share page.
            self._csrf_token = None
            response = self._post_entries(virtual_dir, voucher)
        if response.status_code == 403:
            raise DropboxError(
                f"Dropbox rejected the listing request for {virtual_dir} "
                "(HTTP 403); the shared link may have been removed or made "
                "private"
            )
        if response.status_code == 404:
            raise DropboxError(f"Not a folder in this shared link: {virtual_dir}")
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise DropboxError(
                f"Dropbox returned a non-JSON listing for {virtual_dir}"
            ) from exc

    def _post_entries(self, virtual_dir: str, voucher: str | None):
        """POST one listing request for *virtual_dir*, page *voucher*."""
        payload = {
            "is_xhr": "true",
            "t": self._token(),
            "link_key": self.link_key,
            "link_type": "s",
            "secure_hash": self.secure_hash,
            "sub_path": self._sub_path(virtual_dir),
        }
        if self.rlkey:
            payload["rlkey"] = self.rlkey
        if voucher:
            payload["voucher"] = voucher
        return self.session.post(ENTRIES_URL, data=payload, timeout=DEFAULT_TIMEOUT)

    def _token(self) -> str:
        """Return the CSRF token Dropbox requires, fetching it once if needed."""
        if self._csrf_token is None:
            response = self.session.get(self.share_url, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            token = self.session.cookies.get("__Host-js_csrf") or (
                self.session.cookies.get("t")
            )
            if not token:
                raise DropboxError(
                    f"No CSRF cookie was set by {self.share_url}; the shared "
                    "link may have been removed or made private"
                )
            self._csrf_token = token
        return self._csrf_token

    def _sub_path(self, virtual_dir: str) -> str:
        """Translate a virtual directory path into the API's ``sub_path``."""
        virtual_dir = directory_path(virtual_dir)
        if virtual_dir == self.dataset_root:
            return ""
        relative = relative_to_root(virtual_dir.rstrip("/"), self.dataset_root)
        return f"/{relative.as_posix()}"


def _parse_share_url(share_url: str) -> tuple[str, str, str | None]:
    """Split a shared-folder link into its link key, secure hash, and rlkey.

    Handles both link shapes Dropbox has used for folders:
    ``/scl/fo/<link_key>/<secure_hash>?rlkey=<rlkey>`` and the older
    ``/sh/<link_key>/<secure_hash>``.
    """
    parts = urlsplit(share_url)
    segments = [segment for segment in parts.path.split("/") if segment]
    if segments[:2] == ["scl", "fo"]:
        segments = segments[2:]
    elif segments[:1] == ["sh"]:
        segments = segments[1:]
    else:
        raise DropboxError(
            f"Not a Dropbox shared-folder link: {share_url} (expected a "
            "/scl/fo/<id>/<hash> or /sh/<id>/<hash> path)"
        )
    if len(segments) < 2:
        raise DropboxError(f"Dropbox shared-folder link is incomplete: {share_url}")
    rlkey = dict(parse_qsl(parts.query)).get("rlkey")
    return segments[0], segments[1], rlkey


def _modified_date(timestamp: object) -> str | None:
    """Format a listing entry's epoch-second ``ts`` as an ISO 8601 UTC date."""
    if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _with_query_param(url: str, key: str, value: str) -> str:
    """Return *url* with *key* set to *value*, replacing any existing value."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != key]
    query.append((key, value))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
