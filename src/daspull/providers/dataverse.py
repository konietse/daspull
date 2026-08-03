"""Dependency-light access to a dataset hosted on a Dataverse repository."""

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


class DataverseError(RuntimeError):
    """Raised when a Dataverse dataset cannot be listed or downloaded."""


class DataverseClient:
    """Browse and download a dataset published on a Dataverse repository."""

    def __init__(
        self,
        base_url: str,
        persistent_id: str,
        dataset_root: str,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.persistent_id = persistent_id
        self.dataset_root = dataset_root
        self.session = session or requests.Session()
        self._entries: dict[str, tuple[RemoteFile, int]] | None = None

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

        A Dataverse deposit's file list is fetched whole in one API call
        rather than walked directory by directory, so there is no subtree
        for *descend* to prune; it is accepted only so this method
        interchanges with :meth:`~daspull.providers.pubdas.PubDASClient.iter_files`.
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
            raise DataverseError(f"Not a file in this dataset: {remote_path}")
        return entry[0]

    def download_file(
        self,
        remote: RemoteFile,
        dest: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Download one catalogued file, preserving resumable partial data."""
        file_id = self._catalog()[remote.path][1]
        url = f"{self.base_url}/api/access/datafile/{file_id}"
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
                raise DataverseError(
                    f"{remote.path} could not be downloaded from {self.base_url}; "
                    "it may be a restricted file on this deposit"
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

    def _catalog(self) -> dict[str, tuple[RemoteFile, int]]:
        """Fetch and cache the dataset's full file listing, keyed by path."""
        if self._entries is None:
            document = self._get(
                "/api/datasets/:persistentId/",
                params={"persistentId": self.persistent_id},
            )
            self._entries = dict(self._parse_entries(document))
        return self._entries

    def _parse_entries(
        self, document: dict
    ) -> Iterator[tuple[str, tuple[RemoteFile, int]]]:
        root = directory_path(self.dataset_root)
        for item in document["data"]["latestVersion"]["files"]:
            data_file = item["dataFile"]
            label = item.get("directoryLabel") or ""
            relative = (
                f"{label}/{data_file['filename']}" if label else data_file["filename"]
            )
            path = f"{root}{relative}"
            checksum = data_file.get("checksum") or {}
            remote = RemoteFile(
                path=path,
                size=int(data_file.get("filesize") or 0),
                last_modified=data_file.get("publicationDate"),
                checksum=checksum.get("value"),
            )
            yield path, (remote, data_file["id"])

    def _get(self, path: str, *, params: dict[str, str] | None = None) -> dict:
        response = self.session.get(
            f"{self.base_url}{path}", params=params, timeout=DEFAULT_TIMEOUT
        )
        response.raise_for_status()
        return response.json()
