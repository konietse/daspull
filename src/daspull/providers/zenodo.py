"""Dependency-light access to a dataset hosted on Zenodo."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import requests

from ..catalog import (
    RemoteFile,
    directory_path,
    local_relative_path,
    resolve_literal_path,
)
from ..download import download

DEFAULT_TIMEOUT = (10, 120)


class ZenodoError(RuntimeError):
    """Raised when a Zenodo record cannot be listed or downloaded."""


class ZenodoClient:
    """Browse and download a dataset published as a Zenodo record."""

    def __init__(
        self,
        base_url: str,
        record_id: str,
        dataset_root: str,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.record_id = record_id
        self.dataset_root = dataset_root
        self.session = session or requests.Session()
        self._entries: dict[str, tuple[RemoteFile, str]] | None = None

    def list_files(self, root: str) -> list[RemoteFile]:
        """List every catalogued file below *root*."""
        return sorted(self.iter_files(root), key=lambda item: item.path)

    def iter_files(
        self,
        root: str,
        *,
        descend: Callable[[str], bool] | None = None,
    ) -> Iterator[RemoteFile]:
        """Yield every catalogued file below *root*.

        A Zenodo record's file list is fetched whole in one API call rather
        than walked directory by directory, so there is no subtree for
        *descend* to prune; it is accepted only so this method interchanges
        with the other providers' clients.
        """
        del descend
        root = directory_path(root)
        for remote, _ in self._catalog().values():
            if remote.path.startswith(root):
                yield remote

    def stat_file(self, path: str, *, root: str) -> RemoteFile:
        """Resolve one exact dataset path against the cached file list."""
        remote_path = resolve_literal_path(path, root)
        entry = self._catalog().get(remote_path)
        if entry is None:
            raise ZenodoError(f"Not a file in this record: {remote_path}")
        return entry[0]

    def download_file(
        self,
        remote: RemoteFile,
        dest: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Download one catalogued file, preserving resumable partial data."""
        url = self._catalog()[remote.path][1]
        try:
            return download(
                url,
                dest,
                overwrite=overwrite,
                expected_size=remote.size or None,
                checksum=remote.checksum,
                checksum_algo="md5",
                session=self.session,
            )
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in {401, 403}:
                raise ZenodoError(
                    f"{remote.path} could not be downloaded from {self.base_url}; "
                    "it may be a restricted file on this record"
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

    def _catalog(self) -> dict[str, tuple[RemoteFile, str]]:
        """Fetch and cache the record's full file listing, keyed by path."""
        if self._entries is None:
            document = self._get(f"/api/records/{self.record_id}")
            self._entries = dict(self._parse_entries(document))
        return self._entries

    def _parse_entries(
        self, document: dict
    ) -> Iterator[tuple[str, tuple[RemoteFile, str]]]:
        root = directory_path(self.dataset_root)
        published = document.get("metadata", {}).get("publication_date")
        for item in document["files"]:
            path = f"{root}{item['key']}"
            _, _, digest = str(item.get("checksum") or "").partition(":")
            remote = RemoteFile(
                path=path,
                size=int(item.get("size") or 0),
                last_modified=published,
                checksum=digest or None,
            )
            yield path, (remote, item["links"]["self"])

    def _get(self, path: str, *, params: dict[str, str] | None = None) -> dict:
        response = self.session.get(
            f"{self.base_url}{path}", params=params, timeout=DEFAULT_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
