from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class RemoteFile:
    """A file catalogued below a dataset's root, from any access provider."""

    path: str
    size: int
    last_modified: str | None = None
    checksum: str | None = None

    @property
    def name(self) -> str:
        return PurePosixPath(self.path).name


def select_files(
    files: list[RemoteFile],
    *,
    root: str,
    include: list[str] | tuple[str, ...] = (),
    exclude: list[str] | tuple[str, ...] = (),
) -> list[RemoteFile]:
    """Filter catalog entries with shell-style patterns.

    Patterns are matched against the absolute dataset path, the path relative
    to *root*, and the basename.
    """
    root = directory_path(root)
    selected: list[RemoteFile] = []
    for item in files:
        relative = relative_to_root(item.path, root).as_posix()
        included = not include or any(
            _matches_pattern(item.path, relative, item.name, pattern)
            for pattern in include
        )
        excluded = any(
            _matches_pattern(item.path, relative, item.name, pattern)
            for pattern in exclude
        )
        if included and not excluded:
            selected.append(item)
    return selected


def _matches_pattern(absolute: str, relative: str, name: str, pattern: str) -> bool:
    return (
        fnmatchcase(absolute, pattern)
        or fnmatchcase(relative, pattern)
        or fnmatchcase(name, pattern)
    )


_DRIVE_LETTER_PREFIX = re.compile(r"^[A-Za-z]:")


def clean_remote_path(path: str) -> str:
    """Normalize *path* to an absolute POSIX path, rejecting ``..`` traversal."""
    if "\\" in path:
        raise ValueError(f"Unsafe remote path: {path}")
    candidate = PurePosixPath(f"/{path.lstrip('/')}")
    if ".." in candidate.parts or any(
        _DRIVE_LETTER_PREFIX.match(part) for part in candidate.parts
    ):
        raise ValueError(f"Unsafe remote path: {path}")
    return candidate.as_posix()


def directory_path(path: str) -> str:
    """Normalize *path* to an absolute directory path, with a trailing slash."""
    clean = clean_remote_path(path)
    return clean if clean.endswith("/") else f"{clean}/"


def file_path(path: str) -> str:
    """Normalize *path* to an absolute file path, rejecting a directory path."""
    clean = clean_remote_path(path)
    if clean.endswith("/"):
        raise ValueError(f"Expected a file path, got directory: {path}")
    return clean


def resolve_literal_path(path: str, root: str) -> str:
    """Resolve a literal CLI-supplied path against *root*.

    Accepts either an absolute dataset path or one relative to *root*, and
    validates that it stays inside *root*.
    """
    root = directory_path(root)
    candidate = path if path.startswith("/") else f"{root}{path}"
    remote_path = file_path(candidate)
    relative_to_root(remote_path, root)
    return remote_path


def relative_to_root(path: str, root: str) -> Path:
    """Return *path*'s components below *root*, rejecting paths outside it."""
    remote = PurePosixPath(file_path(path))
    root_path = PurePosixPath(root.rstrip("/"))
    try:
        relative = remote.relative_to(root_path)
    except ValueError as exc:
        raise ValueError(f"{path} is outside dataset root {root}") from exc
    if not relative.parts:
        raise ValueError(f"Expected a file below {root}: {path}")
    return Path(*relative.parts)


_WINDOWS_ILLEGAL_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


def local_relative_path(path: str, root: str) -> Path:
    """Return *path*'s components below *root*, sanitized for a local destination."""
    relative = relative_to_root(path, root)
    return Path(*(_WINDOWS_ILLEGAL_CHARS.sub("_", part) for part in relative.parts))
