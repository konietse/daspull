from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta, timezone

_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")

_INSTANT_HINT = (
    "an exact date and time is required for a buffer, e.g. date='2016-08-12 08:00:00'"
)


def resolve_time_range(
    *,
    date: str | datetime | date_type | None = None,
    start: str | datetime | date_type | None = None,
    end: str | datetime | date_type | None = None,
    buffer: float = 0,
) -> tuple[datetime | None, datetime | None]:
    """Resolve user time arguments into a half-open UTC interval.

    Three mutually exclusive shapes are accepted, mirroring the CLI:

    * ``date="2016"`` / ``"2016-08"`` / ``"2016-08-12"`` -- the whole UTC
      calendar year, month, or day.
    * ``date="2016-08-12 08:00:00"`` (or any :class:`~datetime.datetime`)
      together with ``buffer=SECONDS`` -- one exact UTC moment, widened by
      *buffer* seconds on both sides and inclusive of both ends.
    * ``start=..., end=...`` -- an explicit ``[start, end)`` interval.

    Naive datetimes are read as UTC; aware ones are converted to UTC. With no
    arguments at all, returns ``(None, None)``: no time filtering.
    """
    if buffer < 0:
        raise ValueError("buffer must be at least 0 seconds")
    if date is not None and (start is not None or end is not None):
        raise ValueError("date cannot be combined with start or end")

    if date is not None:
        instant = _instant_or_none(date)
        if instant is None:
            if buffer:
                raise ValueError(_INSTANT_HINT)
            return parse_utc_period(_period_text(date))
        window = timedelta(seconds=buffer)
        # +1us so a zero buffer still selects the block containing `instant`,
        # keeping the half-open [start, end) check inclusive of both ends of
        # the requested window.
        return instant - window, instant + window + timedelta(microseconds=1)

    if buffer:
        raise ValueError(_INSTANT_HINT)
    if (start is None) != (end is None):
        raise ValueError("start and end must be used together")
    if start is None:
        return None, None

    resolved_start = parse_utc_datetime(start, option="start")
    resolved_end = parse_utc_datetime(end, option="end")
    if resolved_end <= resolved_start:
        raise ValueError("the end of a time range must be later than its start")
    return resolved_start, resolved_end


def parse_utc_datetime(
    value: str | datetime | date_type,
    *,
    option: str = "start",
) -> datetime:
    """Read one UTC moment from a string, ``datetime``, or ``date``."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, date_type):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if not isinstance(value, str):
        raise TypeError(
            f"{option} must be a datetime, a date, or a 'YYYY-MM-DD HH:MM:SS' string"
        )

    text = _normalized(value)
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"{option} must use YYYY-MM-DD HH:MM:SS")


def parse_utc_period(value: str) -> tuple[datetime, datetime]:
    """Expand a UTC year, month, or day into a ``[start, end)`` interval."""
    text = value.strip()
    valid_shape = (
        (len(text) == 4 and text.isdigit())
        or (
            len(text) == 7
            and text[4] == "-"
            and text[:4].isdigit()
            and text[5:].isdigit()
        )
        or (
            len(text) == 10
            and text[4] == "-"
            and text[7] == "-"
            and text[:4].isdigit()
            and text[5:7].isdigit()
            and text[8:].isdigit()
        )
    )
    if not valid_shape:
        raise ValueError("date must use YYYY, YYYY-MM, or YYYY-MM-DD")

    try:
        year = int(text[:4])
        if len(text) == 4:
            start = datetime(year, 1, 1, tzinfo=timezone.utc)
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        elif len(text) == 7:
            month = int(text[5:7])
            start = datetime(year, month, 1, tzinfo=timezone.utc)
            if month == 12:
                end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        else:
            start = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end = start + timedelta(days=1)
    except ValueError as exc:
        raise ValueError(f"invalid UTC date: {text}") from exc
    return start, end


def names_an_instant(value: str | datetime | date_type) -> bool:
    """Return whether *value* names an exact moment rather than a calendar period.

    A ``datetime``, or a string carrying a time of day, is an instant; a bare
    ``date`` or a ``YYYY[-MM[-DD]]`` string is a period. The CLI asks this to
    decide whether ``--buffer`` applies, so the two agree by construction.
    """
    if isinstance(value, datetime):
        return True
    if isinstance(value, date_type):
        return False
    if not isinstance(value, str):
        raise TypeError(
            "date must be a datetime, a date, or a "
            "'YYYY[-MM[-DD]]'/'YYYY-MM-DD HH:MM:SS' string"
        )
    text = _normalized(value)
    return " " in text or ":" in text


def _instant_or_none(value: str | datetime | date_type) -> datetime | None:
    """Return the exact moment *value* names, or ``None`` if it names a period."""
    if not names_an_instant(value):
        return None
    return parse_utc_datetime(value, option="date")


def _period_text(value: str | date_type) -> str:
    return _normalized(value) if isinstance(value, str) else value.isoformat()


def _normalized(value: str) -> str:
    return value.strip().replace("T", " ")
