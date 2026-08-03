"""Filename and directory time rules, built from a dataset config's ``layout``."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

Interval = tuple[datetime, datetime]


@dataclass(frozen=True)
class BlockRule:
    """Maps a filename to the UTC interval the file records."""

    pattern: re.Pattern[str]
    timestamp_format: str
    duration: Callable[[re.Match[str], int], timedelta | None]
    pre_roll: timedelta = timedelta(0)

    def interval(self, name: str, size: int) -> Interval | None:
        """Return the interval a matching filename encodes, else ``None``."""
        match = self.pattern.search(name)
        if not match:
            return None
        duration = self.duration(match, size)
        if duration is None:
            return None
        reference = parse_timestamp(match.group(1), self.timestamp_format)
        start = reference - self.pre_roll
        return start, start + duration


@dataclass(frozen=True)
class DirectoryRule:
    """Maps a date-named directory to the UTC span its contents can cover."""

    pattern: re.Pattern[str]
    timestamp_format: str
    span: dict[str, int]
    pad: timedelta

    def interval(self, directory: str) -> Interval | None:
        """Return the span a matching directory covers, else ``None``."""
        match = self.pattern.match(directory)
        if not match:
            return None
        start = parse_timestamp(match.group(1), self.timestamp_format)
        return start - self.pad, advance(start, **self.span) + self.pad


@dataclass(frozen=True)
class SegyBlockLayout:
    """Derives a SEG-Y file's recorded duration from its exact byte size.

    LaFarge's block duration varies per acquisition run and its SEG-Y
    "samples per trace" header fields overflow for the longest blocks, so the
    duration has to be reconstructed from the file's size and the fixed
    trace layout instead of read from a header or assumed constant.
    """

    file_header_bytes: int
    trace_header_bytes: int
    sample_bytes: int
    channels: int
    sample_interval_ms: float

    def duration(self, size: int) -> timedelta | None:
        remaining = size - self.file_header_bytes
        if remaining <= 0 or remaining % self.channels != 0:
            return None
        per_channel = remaining // self.channels - self.trace_header_bytes
        if per_channel <= 0 or per_channel % self.sample_bytes != 0:
            return None
        samples = per_channel // self.sample_bytes
        return timedelta(milliseconds=samples * self.sample_interval_ms)


def block_rules(configs: Sequence[dict]) -> tuple[BlockRule, ...]:
    """Build filename rules from a config's ``layout.blocks`` list."""
    return tuple(_block_rule(config) for config in configs)


def directory_rules(configs: Sequence[dict]) -> tuple[DirectoryRule, ...]:
    """Build directory-pruning rules from a config's ``layout.directories``."""
    return tuple(
        DirectoryRule(
            pattern=re.compile(config["pattern"]),
            timestamp_format=config["timestamp_format"],
            span=dict(config["span"]),
            pad=timedelta(days=config.get("pad_days", 0)),
        )
        for config in configs
    )


def overlaps(interval: Interval, start: datetime, end: datetime) -> bool:
    """Return whether *interval* overlaps the half-open request ``[start, end)``.

    A zero-length interval is an instant rather than a recorded block -- the
    Fairbanks sweep CSVs timestamp an event, not a span -- so it is selected
    when ``start <= instant < end``.
    """
    interval_start, interval_end = interval
    if interval_start == interval_end:
        return start <= interval_start < end
    return interval_end > start and interval_start < end


def advance(moment: datetime, **span: int) -> datetime:
    """Return *moment* moved forward by a calendar span.

    Accepts ``years``, ``months``, ``days``, and ``hours``. Only used for
    directory spans, which always start on a year, month, day, or hour
    boundary, so the month arithmetic never has to clamp a day-of-month.
    """
    months = span.pop("months", 0) + 12 * span.pop("years", 0)
    total = moment.month - 1 + months
    shifted = moment.replace(year=moment.year + total // 12, month=total % 12 + 1)
    return shifted + timedelta(**span)


_DIRECTIVE_WIDTHS = {"%Y": 4, "%y": 2, "%m": 2, "%d": 2, "%H": 2, "%M": 2, "%S": 2}


def parse_timestamp(value: str, timestamp_format: str) -> datetime:
    """Parse a filename or directory timestamp as UTC.

    ``%H`` only accepts 00-23, but Valencia's interrogator names a block
    that crosses midnight with hour 24 rather than wrapping to the next
    day's 00 (e.g. ``2020-09-01_24-01-38``, one minute 38 seconds into
    2020-09-02). Normalize that hour-24 convention to the next day before
    handing the string to ``strptime``.
    """
    value, extra_days = _normalize_hour_24(value, timestamp_format)
    parsed = datetime.strptime(value, timestamp_format).replace(tzinfo=timezone.utc)
    return parsed + timedelta(days=extra_days)


def _normalize_hour_24(value: str, timestamp_format: str) -> tuple[str, int]:
    """Rewrite a literal hour of ``24`` in *value* to ``00``, else pass through."""
    position = 0
    for token in re.findall(r"%[A-Za-z]|[^%]+", timestamp_format):
        if token == "%H":
            if value[position : position + 2] == "24":
                return value[:position] + "00" + value[position + 2 :], 1
            return value, 0
        position += _DIRECTIVE_WIDTHS.get(token, len(token))
    return value, 0


def _block_rule(config: dict) -> BlockRule:
    if "duration_seconds" in config:
        fixed = timedelta(seconds=config["duration_seconds"])

        def duration(match: re.Match[str], size: int) -> timedelta | None:
            """Return the configured constant; the filename and size are irrelevant."""
            return fixed
    elif "duration_from_segy_size" in config:
        segy_layout = SegyBlockLayout(**config["duration_from_segy_size"])

        def duration(match: re.Match[str], size: int) -> timedelta | None:
            """Derive the duration from the file's size; the match is irrelevant."""
            return segy_layout.duration(size)
    else:
        group = config["duration_group"]

        def duration(match: re.Match[str], size: int) -> timedelta | None:
            """Read the block duration in seconds straight from the filename."""
            return timedelta(seconds=int(match.group(group)))

    return BlockRule(
        pattern=re.compile(config["pattern"], re.IGNORECASE),
        timestamp_format=config["timestamp_format"],
        duration=duration,
        # Most filenames timestamp the block's own start, so pre_roll is
        # zero; a few (e.g. SAFOD's cataloged-event filenames) timestamp a
        # reference instant partway into the block instead.
        pre_roll=timedelta(seconds=config.get("pre_roll_seconds", 0)),
    )
