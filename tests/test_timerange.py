from datetime import date, datetime, timedelta, timezone

import pytest

from daspull.timerange import (
    names_an_instant,
    parse_utc_period,
    resolve_time_range,
)

UTC = timezone.utc


@pytest.mark.parametrize(
    ("value", "expected_start", "expected_end"),
    [
        ("2016", "2016-01-01T00:00:00+00:00", "2017-01-01T00:00:00+00:00"),
        ("2016-08", "2016-08-01T00:00:00+00:00", "2016-09-01T00:00:00+00:00"),
        ("2016-12", "2016-12-01T00:00:00+00:00", "2017-01-01T00:00:00+00:00"),
        (
            "2016-08-12",
            "2016-08-12T00:00:00+00:00",
            "2016-08-13T00:00:00+00:00",
        ),
    ],
)
def test_date_precision_maps_to_a_utc_interval(value, expected_start, expected_end):
    start, end = parse_utc_period(value)

    assert start.isoformat() == expected_start
    assert end.isoformat() == expected_end


@pytest.mark.parametrize("value", ["2016-13", "2016-02-30", "16", "2016/08"])
def test_date_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="date must use|invalid UTC date"):
        parse_utc_period(value)


def test_no_arguments_means_no_time_filtering():
    assert resolve_time_range() == (None, None)


def test_calendar_day_expands_to_a_half_open_interval():
    assert resolve_time_range(date="2016-08-12") == (
        datetime(2016, 8, 12, tzinfo=UTC),
        datetime(2016, 8, 13, tzinfo=UTC),
    )


def test_a_bare_date_object_selects_that_whole_day():
    assert resolve_time_range(date=date(2016, 8, 12)) == (
        datetime(2016, 8, 12, tzinfo=UTC),
        datetime(2016, 8, 13, tzinfo=UTC),
    )


def test_an_exact_moment_without_a_buffer_stays_inclusive():
    start, end = resolve_time_range(date="2016-08-12 08:00:00")

    assert start == datetime(2016, 8, 12, 8, tzinfo=UTC)
    assert end == start + timedelta(microseconds=1)


def test_a_buffer_widens_an_exact_moment_symmetrically():
    start, end = resolve_time_range(date="2016-08-12 08:00:00", buffer=30)

    assert start == datetime(2016, 8, 12, 7, 59, 30, tzinfo=UTC)
    assert end == datetime(2016, 8, 12, 8, 0, 30, 1, tzinfo=UTC)


def test_a_datetime_is_treated_as_an_exact_moment():
    start, end = resolve_time_range(date=datetime(2016, 8, 12, 8, tzinfo=UTC), buffer=1)

    assert start == datetime(2016, 8, 12, 7, 59, 59, tzinfo=UTC)
    assert end == datetime(2016, 8, 12, 8, 0, 1, 1, tzinfo=UTC)


def test_a_t_separated_timestamp_is_an_exact_moment():
    start, _ = resolve_time_range(date="2016-08-12T08:00:00")

    assert start == datetime(2016, 8, 12, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "is_instant"),
    [
        ("2016", False),
        ("2016-08", False),
        ("2016-08-12", False),
        ("2016-08-12 08:00:00", True),
        ("2016-08-12T08:00", True),
        (date(2016, 8, 12), False),
        (datetime(2016, 8, 12, 8, tzinfo=UTC), True),
    ],
)
def test_an_instant_is_told_apart_from_a_calendar_period(value, is_instant):
    assert names_an_instant(value) is is_instant


def test_a_buffer_requires_an_exact_moment():
    with pytest.raises(ValueError, match="exact date and time"):
        resolve_time_range(date="2016-08-12", buffer=30)


def test_a_buffer_without_any_date_is_rejected():
    with pytest.raises(ValueError, match="exact date and time"):
        resolve_time_range(buffer=30)


def test_a_negative_buffer_is_rejected():
    with pytest.raises(ValueError, match="at least 0"):
        resolve_time_range(date="2016-08-12 08:00:00", buffer=-1)


def test_an_explicit_interval_is_kept_as_given():
    assert resolve_time_range(
        start="2016-08-05 07:31:15", end="2016-10-03 10:09:21"
    ) == (
        datetime(2016, 8, 5, 7, 31, 15, tzinfo=UTC),
        datetime(2016, 10, 3, 10, 9, 21, tzinfo=UTC),
    )


def test_a_naive_datetime_is_read_as_utc():
    naive = datetime(2016, 8, 5, 7, 31, 15, tzinfo=None)  # noqa: DTZ001
    start, _ = resolve_time_range(start=naive, end="2016-08-06 00:00:00")

    assert start == datetime(2016, 8, 5, 7, 31, 15, tzinfo=UTC)


def test_an_aware_datetime_is_converted_to_utc():
    berlin = timezone(timedelta(hours=2))
    start, _ = resolve_time_range(
        start=datetime(2016, 8, 5, 9, 31, 15, tzinfo=berlin),
        end=datetime(2016, 8, 6, tzinfo=UTC),
    )

    assert start == datetime(2016, 8, 5, 7, 31, 15, tzinfo=UTC)


def test_date_cannot_be_combined_with_an_explicit_interval():
    with pytest.raises(ValueError, match="cannot be combined"):
        resolve_time_range(
            date="2016-08", start="2016-08-01 00:00:00", end="2016-09-01 00:00:00"
        )


def test_an_interval_needs_both_boundaries():
    with pytest.raises(ValueError, match="must be used together"):
        resolve_time_range(start="2016-08-05 07:31:15")


def test_a_reversed_interval_is_rejected():
    with pytest.raises(ValueError, match="later than"):
        resolve_time_range(start="2016-08-06 00:00:00", end="2016-08-05 00:00:00")


def test_a_malformed_timestamp_names_the_expected_format():
    with pytest.raises(ValueError, match="YYYY-MM-DD HH:MM:SS"):
        resolve_time_range(start="05.08.2016 07:31", end="2016-08-06 00:00:00")


def test_a_wrongly_typed_boundary_raises_a_type_error():
    with pytest.raises(TypeError):
        resolve_time_range(start=1470382275, end="2016-08-06 00:00:00")
