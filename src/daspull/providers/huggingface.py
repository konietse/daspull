"""Dependency-light access to a dataset hosted in a Hugging Face dataset repo."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import requests

from ..catalog import (
    RemoteFile,
    directory_path,
    local_relative_path,
    resolve_literal_path,
)
from ..download import download

DEFAULT_TIMEOUT = (10, 120)
DEFAULT_REVISION = "main"
_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


class HuggingFaceError(RuntimeError):
    """Raised when a Hugging Face repo cannot be listed or downloaded from."""


@dataclass(frozen=True)
class _Entry:
    path: str
    is_dir: bool
    size: int = 0
    checksum: str | None = None


class HuggingFaceClient:
    """Browse and download a dataset stored under one prefix of a HF repo."""

    def __init__(
        self,
        base_url: str,
        repo_id: str,
        prefix: str,
        dataset_root: str,
        *,
        revision: str = DEFAULT_REVISION,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.repo_id = repo_id.strip("/")
        self.prefix = "" if not prefix else directory_path(prefix).lstrip("/")
        self.dataset_root = directory_path(dataset_root)
        self.revision = revision or DEFAULT_REVISION
        self.session = session or requests.Session()

    def list_files(self, root: str) -> list[RemoteFile]:
        """Recursively list files below *root* in the repo."""
        return sorted(self.iter_files(root), key=lambda item: item.path)

    def iter_files(
        self,
        root: str,
        *,
        descend: Callable[[str], bool] | None = None,
    ) -> Iterator[RemoteFile]:
        """Yield files while recursively traversing *root*.

        Each directory level is one (possibly paged) tree request scoped to
        that directory, so *descend* genuinely prunes subtrees instead of only
        filtering an already-fetched catalog.
        """
        pending = deque([directory_path(root)])
        visited: set[str] = set()

        while pending:
            virtual_dir = pending.popleft()
            if virtual_dir in visited:
                continue
            visited.add(virtual_dir)
            for entry in self._list_directory(self._real_prefix(virtual_dir)):
                virtual = self._virtual_path(entry.path)
                if entry.is_dir:
                    child = directory_path(virtual)
                    if descend is None or descend(child):
                        pending.append(child)
                else:
                    yield RemoteFile(
                        path=virtual,
                        size=entry.size,
                        checksum=entry.checksum,
                    )

    def stat_file(self, path: str, *, root: str) -> RemoteFile:
        """Resolve one exact dataset path from the download redirect, no listing."""
        remote_path = resolve_literal_path(path, root)
        response = self.session.head(
            self._file_url(self._real_path(remote_path)),
            timeout=DEFAULT_TIMEOUT,
            allow_redirects=False,
        )
        if response.status_code == 404:
            raise HuggingFaceError(f"Not a file in this repo: {remote_path}")
        if response.status_code not in _REDIRECT_STATUS_CODES:
            response.raise_for_status()
        # An LFS file answers with a redirect carrying the real size and its
        # SHA-256; a small, plain git file answers 200 with its own headers
        # and no content hash daspull could verify.
        size = response.headers.get("x-linked-size") or response.headers.get(
            "content-length"
        )
        return RemoteFile(
            path=remote_path,
            size=int(size or 0),
            last_modified=response.headers.get("last-modified"),
            checksum=_sha256_from_etag(response.headers.get("x-linked-etag")),
        )

    def download_file(
        self,
        remote: RemoteFile,
        dest: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Download one catalogued file, preserving resumable partial data."""
        return download(
            self._file_url(self._real_path(remote.path)),
            dest,
            overwrite=overwrite,
            expected_size=remote.size or None,
            checksum=remote.checksum,
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

    def _list_directory(self, real_prefix: str) -> Iterator[_Entry]:
        """Yield one directory level's immediate children (files and subdirs)."""
        url = self._tree_url(real_prefix)
        while url:
            response = self.session.get(url, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 404:
                raise HuggingFaceError(
                    f"Not a directory in this repo: {real_prefix or '/'} "
                    f"({response.headers.get('x-error-message', 'not found')})"
                )
            response.raise_for_status()
            for item in response.json():
                entry = _entry_from(item)
                if entry is not None:
                    yield entry
            url = _next_page(response.headers.get("link"))

    def _tree_url(self, real_prefix: str) -> str:
        # A trailing slash makes the tree endpoint answer with a redirect
        # instead of the listing, so the repo root is addressed without one.
        path = _quote(real_prefix.rstrip("/"))
        return (
            f"{self.base_url}/api/datasets/{self.repo_id}/tree/"
            f"{_quote(self.revision)}/{path}"
        ).rstrip("/")

    def _file_url(self, real_path: str) -> str:
        return (
            f"{self.base_url}/datasets/{self.repo_id}/resolve/"
            f"{_quote(self.revision)}/{_quote(real_path)}"
        )

    def _real_prefix(self, virtual_dir: str) -> str:
        return f"{self.prefix}{self._below_root(directory_path(virtual_dir))}"

    def _real_path(self, virtual_path: str) -> str:
        return f"{self.prefix}{self._below_root(virtual_path)}"

    def _below_root(self, virtual: str) -> str:
        if not virtual.startswith(self.dataset_root):
            raise HuggingFaceError(
                f"{virtual} is outside dataset root {self.dataset_root}"
            )
        return virtual[len(self.dataset_root) :]

    def _virtual_path(self, real_path: str) -> str:
        if not real_path.startswith(self.prefix):
            raise HuggingFaceError(f"{real_path} is outside repo prefix {self.prefix}")
        return f"{self.dataset_root}{real_path[len(self.prefix) :]}"


def _entry_from(item: dict) -> _Entry | None:
    """Turn one raw tree entry into an :class:`_Entry`, skipping unknown kinds."""
    path = item.get("path")
    kind = item.get("type")
    if not path or kind not in {"file", "directory"}:
        return None
    if kind == "directory":
        return _Entry(path=path, is_dir=True)
    lfs = item.get("lfs") or {}
    return _Entry(
        path=path,
        is_dir=False,
        size=int(lfs.get("size") or item.get("size") or 0),
        # Only an LFS oid is the content's SHA-256; a plain file's `oid` is a
        # git blob SHA-1, which would never match what `download` computes.
        checksum=lfs.get("oid"),
    )


def _next_page(link_header: str | None) -> str | None:
    """Return the ``rel="next"`` URL from a ``Link`` header, if there is one."""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' not in part:
            continue
        target = part.split(">", 1)[0].strip()
        if target.startswith("<"):
            return target[1:]
    return None


def _sha256_from_etag(etag: str | None) -> str | None:
    """Return a quoted ``x-linked-etag`` as a plain SHA-256 hex digest."""
    if not etag:
        return None
    value = etag.strip('"')
    return value if len(value) == 64 else None


def _quote(value: str) -> str:
    return quote(value, safe="/")
