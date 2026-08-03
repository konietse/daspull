"""The interface every access-provider client implements."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol

from .catalog import RemoteFile


class DatasetClient(Protocol):
    """A client that can list, resolve, and download one dataset's files."""

    def iter_files(
        self,
        root: str,
        *,
        descend: Callable[[str], bool] | None = None,
    ) -> Iterator[RemoteFile]: ...

    def stat_file(self, path: str, *, root: str) -> RemoteFile: ...

    def download_files(
        self,
        files: list[RemoteFile],
        dest_dir: str | Path,
        *,
        root: str,
        overwrite: bool = False,
    ) -> list[Path]: ...
