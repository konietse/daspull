from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

STANFORD_2 = DATASETS["stanford_2"]


def test_segy_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/Stanford-2-Sandhill-Road/Data/20200301/"
        "cbt_processed_20200301_065859.550+0000.sgy",
        75303600,
    )

    assert STANFORD_2.file_is_in_time_range(
        remote,
        start=utc("2020-03-01 06:59:00.000"),
        end=utc("2020-03-01 06:59:01.000"),
    )
    assert not STANFORD_2.file_is_in_time_range(
        remote,
        start=utc("2020-03-01 07:00:00.000"),
        end=utc("2020-03-01 07:01:00.000"),
    )


def test_segy_block_interval_keeps_the_filename_milliseconds():
    remote = RemoteFile(
        "/Stanford-2-Sandhill-Road/Data/20200301/"
        "cbt_processed_20200301_065859.550+0000.sgy",
        75303600,
    )

    assert STANFORD_2.block_interval(remote) == (
        utc("2020-03-01 06:58:59.550"),
        utc("2020-03-01 06:59:59.550"),
    )
    assert (
        STANFORD_2.block_interval(RemoteFile("/Stanford-2-Sandhill-Road/readme.txt", 1))
        is None
    )


def test_continuous_intervals_merge_adjacent_blocks_and_keep_gaps():
    files = [
        RemoteFile(
            "/Stanford-2-Sandhill-Road/Data/20200301/"
            "cbt_processed_20200301_065959.550+0000.sgy",
            75303600,
        ),
        RemoteFile(
            "/Stanford-2-Sandhill-Road/Data/20200301/"
            "cbt_processed_20200301_065859.550+0000.sgy",
            75303600,
        ),
        RemoteFile(
            "/Stanford-2-Sandhill-Road/Data/20200314/"
            "cbt_processed_20200314_055931.699+0000.sgy",
            75303600,
        ),
    ]

    assert STANFORD_2.continuous_intervals(files) == [
        (utc("2020-03-01 06:58:59.550"), utc("2020-03-01 07:00:59.550")),
        (utc("2020-03-14 05:59:31.699"), utc("2020-03-14 06:00:31.699")),
    ]


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/Stanford-2-Sandhill-Road/citation.txt", 2653)

    assert not STANFORD_2.file_is_in_time_range(
        remote,
        start=utc("2020-03-01 00:00:00.000"),
        end=utc("2020-03-02 00:00:00.000"),
    )


def test_daily_directory_pruning_keeps_a_day_of_slack_for_local_time_offsets():
    requested = {
        "start": utc("2020-03-02 00:00:00.000"),
        "end": utc("2020-03-03 00:00:00.000"),
    }

    assert STANFORD_2.directory_may_overlap_time_range(
        "/Stanford-2-Sandhill-Road/Data/20200301/",
        **requested,
    )
    assert STANFORD_2.directory_may_overlap_time_range(
        "/Stanford-2-Sandhill-Road/Data/20200302/",
        **requested,
    )
    assert STANFORD_2.directory_may_overlap_time_range(
        "/Stanford-2-Sandhill-Road/Data/20200303/",
        **requested,
    )
    assert not STANFORD_2.directory_may_overlap_time_range(
        "/Stanford-2-Sandhill-Road/Data/20200310/",
        **requested,
    )
    assert STANFORD_2.directory_may_overlap_time_range(
        "/Stanford-2-Sandhill-Road/Data/",
        **requested,
    )
