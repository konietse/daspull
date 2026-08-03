"""Dependency-light access to a dataset hosted on a public AWS S3 bucket."""

from __future__ import annotations

import xml.etree.ElementTree as ET
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
_S3_NAMESPACE = "{http://s3.amazonaws.com/doc/2006-03-01/}"


class S3Error(RuntimeError):
    """Raised when an S3 bucket cannot be listed or downloaded from."""


@dataclass(frozen=True)
class _Entry:
    key: str
    is_dir: bool
    size: int = 0
    etag: str | None = None
    last_modified: str | None = None


class S3Client:
    """Browse and download a dataset published under one prefix of a public
    S3 bucket."""

    def __init__(
        self,
        base_url: str,
        prefix: str,
        dataset_root: str,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.prefix = prefix if prefix.endswith("/") else f"{prefix}/"
        self.dataset_root = dataset_root
        self.session = session or requests.Session()

    def list_files(self, root: str) -> list[RemoteFile]:
        """Recursively list files below *root* in the bucket."""
        return sorted(self.iter_files(root), key=lambda item: item.path)

    def iter_files(
        self,
        root: str,
        *,
        descend: Callable[[str], bool] | None = None,
    ) -> Iterator[RemoteFile]:
        """Yield files while recursively traversing *root*.

        Each directory listed is one or more paginated ``ListObjectsV2``
        requests scoped to that directory's real key prefix, so *descend*
        genuinely prunes subtrees the caller doesn't need -- unlike the
        Dataverse/Zenodo clients, where the whole catalog is already fetched
        by the time ``descend`` could apply.
        """
        pending = deque([directory_path(root)])
        visited: set[str] = set()

        while pending:
            virtual_dir = pending.popleft()
            if virtual_dir in visited:
                continue
            visited.add(virtual_dir)
            for entry in self._list_directory(self._real_prefix(virtual_dir)):
                if entry.is_dir:
                    child = self._virtual_path(entry.key)
                    if descend is None or descend(child):
                        pending.append(child)
                else:
                    yield RemoteFile(
                        path=self._virtual_path(entry.key),
                        size=entry.size,
                        last_modified=entry.last_modified,
                        checksum=_checksum_from_etag(entry.etag),
                    )

    def stat_file(self, path: str, *, root: str) -> RemoteFile:
        """Resolve one exact dataset path via a HEAD request, no listing."""
        remote_path = resolve_literal_path(path, root)
        url = self._object_url(self._real_key(remote_path))
        response = self.session.head(url, timeout=DEFAULT_TIMEOUT)
        if response.status_code == 404:
            raise S3Error(f"Not a file in this bucket: {remote_path}")
        response.raise_for_status()
        return RemoteFile(
            path=remote_path,
            size=int(response.headers.get("Content-Length") or 0),
            last_modified=response.headers.get("Last-Modified"),
            checksum=_checksum_from_etag(response.headers.get("ETag")),
        )

    def download_file(
        self,
        remote: RemoteFile,
        dest: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Download one catalogued file, preserving resumable partial data."""
        url = self._object_url(self._real_key(remote.path))
        return download(
            url,
            dest,
            overwrite=overwrite,
            expected_size=remote.size or None,
            checksum=remote.checksum,
            checksum_algo="md5",
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
        token: str | None = None
        while True:
            params = {"list-type": "2", "prefix": real_prefix, "delimiter": "/"}
            if token:
                params["continuation-token"] = token
            response = self.session.get(
                self.base_url + "/", params=params, timeout=DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for node in root.findall(f"{_S3_NAMESPACE}CommonPrefixes"):
                key = node.findtext(f"{_S3_NAMESPACE}Prefix")
                if key:
                    yield _Entry(key=key, is_dir=True)
            for node in root.findall(f"{_S3_NAMESPACE}Contents"):
                key = node.findtext(f"{_S3_NAMESPACE}Key")
                if not key or key == real_prefix:
                    continue
                size = int(node.findtext(f"{_S3_NAMESPACE}Size") or 0)
                etag = node.findtext(f"{_S3_NAMESPACE}ETag")
                last_modified = node.findtext(f"{_S3_NAMESPACE}LastModified")
                yield _Entry(
                    key=key,
                    is_dir=False,
                    size=size,
                    etag=etag,
                    last_modified=last_modified,
                )
            truncated = root.findtext(f"{_S3_NAMESPACE}IsTruncated") == "true"
            if not truncated:
                return
            token = root.findtext(f"{_S3_NAMESPACE}NextContinuationToken")

    def _real_prefix(self, virtual_dir: str) -> str:
        dataset_root = directory_path(self.dataset_root)
        suffix = directory_path(virtual_dir)[len(dataset_root) :]
        return f"{self.prefix}{suffix}"

    def _real_key(self, virtual_path: str) -> str:
        dataset_root = directory_path(self.dataset_root)
        return f"{self.prefix}{virtual_path[len(dataset_root) :]}"

    def _virtual_path(self, real_key: str) -> str:
        dataset_root = directory_path(self.dataset_root)
        return f"{dataset_root}{real_key[len(self.prefix) :]}"

    def _object_url(self, real_key: str) -> str:
        return f"{self.base_url}/{quote(real_key, safe='/')}"


def _checksum_from_etag(etag: str | None) -> str | None:
    """Return an S3 ETag as an MD5 digest, or ``None`` if it isn't one.

    A multipart upload's ETag (``"<hex>-<part-count>"``) is not the file's
    MD5 and must not be used for checksum verification; only a plain,
    single-part ETag is a real MD5.
    """
    if not etag:
        return None
    value = etag.strip('"')
    if "-" in value:
        return None
    return value
