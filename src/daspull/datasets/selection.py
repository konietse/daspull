from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import datetime
from functools import partial
from pathlib import Path

from ..catalog import RemoteFile, select_files
from ..client import DatasetClient
from .acquisition import AcquisitionConfig
from .layout import Interval
from .registry import DatasetSpec


def is_exact_selection(patterns: Sequence[str]) -> bool:
    """Return whether every pattern is a literal path with no glob wildcards."""
    return bool(patterns) and all(not _has_glob_magic(pattern) for pattern in patterns)


def _has_glob_magic(value: str) -> bool:
    return any(character in value for character in "*?[")


def stat_dataset_files(
    client: DatasetClient,
    dataset: DatasetSpec,
    paths: Iterable[str],
    *,
    exclude: Sequence[str] = (),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
    configurations: Sequence[AcquisitionConfig] = (),
) -> list[RemoteFile]:
    """Resolve literal dataset paths directly, without scanning the catalog."""
    include = list(dict.fromkeys(paths))
    files = [client.stat_file(path, root=dataset.dataset_root) for path in include]
    selected = select_files(
        files, root=dataset.dataset_root, include=include, exclude=exclude
    )
    selected = [
        remote
        for remote in selected
        if dataset.file_used_configurations(remote, configurations)
    ]
    if start is not None:
        selected = [
            remote
            for remote in selected
            if dataset.file_is_in_time_range(remote, start=start, end=end)
        ]
    if limit is not None:
        selected = selected[:limit]
    return selected


def scan_dataset_files(
    client: DatasetClient,
    dataset: DatasetSpec,
    *,
    root: str,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
    configurations: Sequence[AcquisitionConfig] = (),
) -> Iterator[RemoteFile]:
    """Recursively scan *root*, yielding matching files as they're found."""
    descend = _descend(dataset, start=start, end=end, configurations=configurations)
    count = 0
    for remote in client.iter_files(root=root, descend=descend):
        if not select_files(
            [remote], root=dataset.dataset_root, include=include, exclude=exclude
        ):
            continue
        if start is not None and not dataset.file_is_in_time_range(
            remote, start=start, end=end
        ):
            continue
        if not dataset.file_used_configurations(remote, configurations):
            continue
        yield remote
        count += 1
        if limit is not None and count >= limit:
            return


def _descend(
    dataset: DatasetSpec,
    *,
    start: datetime | None,
    end: datetime | None,
    configurations: Sequence[AcquisitionConfig],
) -> Callable[[str], bool] | None:
    """Build the scan's directory filter, or ``None`` when nothing prunes.

    Two independent reasons to skip a subtree -- it cannot hold the requested
    dates, or it cannot hold the requested acquisition settings -- combine
    here so a client's ``descend`` callback stays a single predicate.
    """
    tests: list[Callable[[str], bool]] = []
    if start is not None:
        tests.append(
            partial(dataset.directory_may_overlap_time_range, start=start, end=end)
        )
    if any(config.root is not None for config in configurations):
        tests.append(
            partial(dataset.directory_may_hold_configurations, configs=configurations)
        )
    if not tests:
        return None
    return lambda directory: all(test(directory) for test in tests)


def select_dataset_files(
    client: DatasetClient,
    dataset: DatasetSpec,
    *,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
    include_all_file_types: bool = False,
    configurations: Sequence[AcquisitionConfig] = (),
) -> list[RemoteFile]:
    """Select dataset files in a single call, the same way the CLI does.

    Without *include*, selects the dataset's primary file type (or, with
    ``include_all_file_types=True``, every file under the dataset root).
    Literal glob-free *include* paths resolve directly via one ``stat`` call
    each; anything else triggers a full recursive catalog scan.
    """
    if include:
        patterns = list(include)
    elif include_all_file_types:
        patterns = []
    else:
        patterns = [dataset.primary_pattern]

    if is_exact_selection(patterns):
        return stat_dataset_files(
            client,
            dataset,
            patterns,
            exclude=exclude,
            start=start,
            end=end,
            limit=limit,
            configurations=configurations,
        )

    root = (
        dataset.primary_root
        if not include and not include_all_file_types
        else dataset.dataset_root
    )
    return list(
        scan_dataset_files(
            client,
            dataset,
            root=root,
            include=patterns,
            exclude=exclude,
            start=start,
            end=end,
            limit=limit,
            configurations=configurations,
        )
    )


def continuous_dataset_intervals(
    client: DatasetClient,
    dataset: DatasetSpec,
    *,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    start: datetime | None = None,
    end: datetime | None = None,
    configurations: Sequence[AcquisitionConfig] = (),
) -> list[Interval]:
    """Return the dataset's continuous UTC coverage intervals (``--list-intervals``)."""
    patterns = list(include) if include else [dataset.primary_pattern]
    files = scan_dataset_files(
        client,
        dataset,
        root=dataset.primary_root,
        include=patterns,
        exclude=exclude,
        start=start,
        end=end,
        configurations=configurations,
    )
    return dataset.continuous_intervals(files)


def download_dataset_files(
    client: DatasetClient,
    dataset: DatasetSpec,
    files: list[RemoteFile],
    dest_dir: str | Path,
    *,
    overwrite: bool = False,
) -> list[Path]:
    """Download dataset files, preserving their tree below *dest_dir*."""
    return client.download_files(
        files, dest_dir, root=dataset.dataset_root, overwrite=overwrite
    )
