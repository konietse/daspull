from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

FAIRBANKS = DATASETS["fairbanks"]


def test_tdms_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/Fairbanks/Data/tdms/day/aug4_160805073115.tdms",
        100,
    )

    assert FAIRBANKS.file_is_in_time_range(
        remote,
        start=utc("2016-08-05 07:31:30"),
        end=utc("2016-08-05 07:31:31"),
    )
    assert not FAIRBANKS.file_is_in_time_range(
        remote,
        start=utc("2016-08-05 07:32:15"),
        end=utc("2016-08-05 07:33:15"),
    )


def test_tdms_block_interval_uses_filename_start_and_sixty_second_duration():
    remote = RemoteFile(
        "/Fairbanks/Data/tdms/day/aug4_160805073115.tdms",
        100,
    )

    assert FAIRBANKS.block_interval(remote) == (
        utc("2016-08-05 07:31:15"),
        utc("2016-08-05 07:32:15"),
    )
    assert FAIRBANKS.block_interval(RemoteFile("/Fairbanks/citation.txt", 1)) is None


def test_sweep_csv_timestamp_is_a_zero_length_instant():
    remote = RemoteFile("/Fairbanks/Data/sweeps/day/SRU2_20160805073218.csv", 100)

    assert FAIRBANKS.block_interval(remote) == (
        utc("2016-08-05 07:32:18"),
        utc("2016-08-05 07:32:18"),
    )


def test_continuous_tdms_intervals_merge_adjacent_blocks_and_keep_gaps():
    files = [
        RemoteFile("/Fairbanks/aug4_160805073416.tdms", 100),
        RemoteFile("/Fairbanks/aug4_160805073215.tdms", 100),
        RemoteFile("/Fairbanks/aug4_160805073115.tdms", 100),
        RemoteFile("/Fairbanks/SRU2_20160805073218.csv", 100),
    ]

    assert FAIRBANKS.continuous_intervals(files) == [
        (utc("2016-08-05 07:31:15"), utc("2016-08-05 07:33:15")),
        (utc("2016-08-05 07:34:16"), utc("2016-08-05 07:35:16")),
    ]


def test_time_range_end_is_exclusive_for_sweeps():
    remote = RemoteFile(
        "/Fairbanks/Data/sweeps/day/SRU2_20160805073218.csv",
        100,
    )

    assert FAIRBANKS.file_is_in_time_range(
        remote,
        start=utc("2016-08-05 07:32:18"),
        end=utc("2016-08-05 07:32:19"),
    )
    assert not FAIRBANKS.file_is_in_time_range(
        remote,
        start=utc("2016-08-05 07:31:18"),
        end=utc("2016-08-05 07:32:18"),
    )


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/Fairbanks/citation.txt", 734)

    assert not FAIRBANKS.file_is_in_time_range(
        remote,
        start=utc("2016-08-05 00:00:00"),
        end=utc("2016-08-06 00:00:00"),
    )


def test_daily_directory_pruning_uses_utc_calendar_day():
    requested = {
        "start": utc("2016-08-05 07:31:15"),
        "end": utc("2016-08-06 07:31:15"),
    }

    assert FAIRBANKS.directory_may_overlap_time_range(
        "/Fairbanks/Data/tdms/20160805073201_data/",
        **requested,
    )
    assert FAIRBANKS.directory_may_overlap_time_range(
        "/Fairbanks/Data/tdms/20160806073211_data/",
        **requested,
    )
    assert not FAIRBANKS.directory_may_overlap_time_range(
        "/Fairbanks/Data/tdms/20160807073213_data/",
        **requested,
    )
    assert FAIRBANKS.directory_may_overlap_time_range(
        "/Fairbanks/Data/tdms/",
        **requested,
    )
