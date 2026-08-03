from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

RIDGECREST_NORTH = DATASETS["ridgecrest_north"]


def test_block_interval_uses_filename_start_and_one_hour_duration():
    remote = RemoteFile("/RidgecrestNorth/SEG-Y/hourly/2020062417.segy", 4500303600)

    assert RIDGECREST_NORTH.block_interval(remote) == (
        utc("2020-06-24 17:00:00"),
        utc("2020-06-24 18:00:00"),
    )


def test_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile("/RidgecrestNorth/SEG-Y/hourly/2020062417.segy", 4500303600)

    assert RIDGECREST_NORTH.file_is_in_time_range(
        remote,
        start=utc("2020-06-24 17:40:00"),
        end=utc("2020-06-24 17:41:00"),
    )
    assert not RIDGECREST_NORTH.file_is_in_time_range(
        remote,
        start=utc("2020-06-24 18:00:00"),
        end=utc("2020-06-24 19:00:00"),
    )


def test_time_range_excludes_files_without_a_timestamp():
    for remote in (
        RemoteFile("/RidgecrestNorth/das_info.csv", 35471),
        RemoteFile("/RidgecrestNorth/README_citation.txt", 594),
    ):
        assert not RIDGECREST_NORTH.file_is_in_time_range(
            remote,
            start=utc("2020-06-20 00:00:00"),
            end=utc("2020-07-30 00:00:00"),
        )
        assert RIDGECREST_NORTH.block_interval(remote) is None


def test_continuous_intervals_merge_adjacent_hours_and_keep_a_gap():
    files = [
        RemoteFile("/RidgecrestNorth/SEG-Y/hourly/2020062301.segy", 4500303600),
        RemoteFile("/RidgecrestNorth/SEG-Y/hourly/2020062300.segy", 4500303600),
        # a real gap in the archive: all of 2020-06-30 is missing
        RemoteFile("/RidgecrestNorth/SEG-Y/hourly/2020070100.segy", 4500303600),
    ]

    assert RIDGECREST_NORTH.continuous_intervals(files) == [
        (utc("2020-06-23 00:00:00"), utc("2020-06-23 02:00:00")),
        (utc("2020-07-01 00:00:00"), utc("2020-07-01 01:00:00")),
    ]


def test_no_directory_pruning_rules_are_configured():
    # SEG-Y/hourly/ is a flat prefix (verified via a full bucket listing), so
    # there is nothing to prune on and every directory is always a candidate.
    assert not RIDGECREST_NORTH.directories
    assert RIDGECREST_NORTH.directory_may_overlap_time_range(
        "/RidgecrestNorth/SEG-Y/hourly/",
        start=utc("2020-06-20 00:00:00"),
        end=utc("2020-07-30 00:00:00"),
    )
