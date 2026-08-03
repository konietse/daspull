from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

SAFOD = DATASETS["safod"]


def test_block_starts_ten_seconds_before_the_filename_timestamp():
    remote = RemoteFile("/SAFOD/2017-06-23T02:54:50.560000Z_mag0.7.npy", 47996928)

    assert SAFOD.block_interval(remote) == (
        utc("2017-06-23 02:54:40.560000"),
        utc("2017-06-23 02:55:40.556000"),
    )


def test_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile("/SAFOD/2017-06-23T02:54:50.560000Z_mag0.7.npy", 47996928)

    # 5 s before the event timestamp, well within the 10 s pre-roll.
    assert SAFOD.file_is_in_time_range(
        remote,
        start=utc("2017-06-23 02:54:45.000000"),
        end=utc("2017-06-23 02:54:46.000000"),
    )
    assert not SAFOD.file_is_in_time_range(
        remote,
        start=utc("2017-06-23 02:50:00.000000"),
        end=utc("2017-06-23 02:51:00.000000"),
    )


def test_double_precision_magunknown_file_has_the_same_duration():
    # Stored as float64 (double the bytes of every other file) but the same
    # 800-channel x 14,999-sample window, so its interval must match exactly.
    remote = RemoteFile("/SAFOD/2017-07-01T03:15:13.538000Z_magUNKNOWN.npy", 95993728)

    assert SAFOD.block_interval(remote) == (
        utc("2017-07-01 03:15:03.538000"),
        utc("2017-07-01 03:16:03.534000"),
    )


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/SAFOD/notes.txt", 100)

    assert not SAFOD.file_is_in_time_range(
        remote,
        start=utc("2017-06-01 00:00:00"),
        end=utc("2017-08-01 00:00:00"),
    )
    assert SAFOD.block_interval(remote) is None


def test_continuous_intervals_treat_separate_events_as_separate_coverage():
    files = [
        RemoteFile("/SAFOD/2017-06-23T02:54:50.560000Z_mag0.7.npy", 47996928),
        RemoteFile("/SAFOD/2017-06-23T14:31:15.170000Z_mag0.77.npy", 47996928),
    ]

    assert SAFOD.continuous_intervals(files) == [
        (utc("2017-06-23 02:54:40.560000"), utc("2017-06-23 02:55:40.556000")),
        (utc("2017-06-23 14:31:05.170000"), utc("2017-06-23 14:32:05.166000")),
    ]


def test_no_directory_pruning_rules_are_configured():
    assert not SAFOD.directories
    assert SAFOD.directory_may_overlap_time_range(
        "/SAFOD/",
        start=utc("2017-06-01 00:00:00"),
        end=utc("2017-08-01 00:00:00"),
    )
