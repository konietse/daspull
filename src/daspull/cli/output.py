"""Everything the dataset subcommands print.

Listings stream as they are found (a full catalog scan can take minutes), so
each line is flushed rather than buffered until the scan ends.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..catalog import RemoteFile
from ..datasets.layout import Interval


def print_file(item: RemoteFile) -> None:
    """Print one catalog entry: its size, right-aligned, and its path."""
    print(f"{item.size:>14}  {item.path}", flush=True)


def print_file_list(files: Sequence[RemoteFile]) -> None:
    """Print every entry, then the totals line."""
    for item in files:
        print_file(item)
    print_file_summary(files)


def print_file_summary(files: Sequence[RemoteFile]) -> None:
    """Print the file count and total transfer size."""
    total = sum(item.size for item in files)
    print(f"{len(files)} file(s), {_format_size(total)} total")


def print_time_intervals(intervals: Sequence[Interval]) -> None:
    """Print the dataset's continuous UTC coverage as a two-column table."""
    print("START UTC (inclusive)    END UTC (exclusive)")
    for start, end in intervals:
        print(f"{start:%Y-%m-%d %H:%M:%S}    {end:%Y-%m-%d %H:%M:%S}")
    print(f"{len(intervals)} interval(s)")


def _format_size(size: int) -> str:
    """Format a byte count in decimal (SI) units, matching the rest of
    daspull -- README's dataset table and each config's ``data.size_gb`` are
    both base-1000, not base-1024. Once the total reaches a full terabyte,
    also show it in GB alongside: most of the datasets here are TB-scale, and
    a bare TB figure is harder to relate to disk-space numbers than GB is.
    """
    gb = size / 1_000_000_000
    if gb >= 1000:
        return f"{gb / 1000:.2f} TB ({gb:,.1f} GB)"
    if gb >= 1:
        return f"{gb:.2f} GB"
    mb = size / 1_000_000
    if mb >= 1:
        return f"{mb:.1f} MB"
    kb = size / 1_000
    if kb >= 1:
        return f"{kb:.1f} KB"
    return f"{size} B"
