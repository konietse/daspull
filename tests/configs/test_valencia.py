from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

VALENCIA = DATASETS["valencia"]


def test_hdf5_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/Valencia/Data/SR_Valencia_2020-09-01_13-21-28_UTC/"
        "SR_Valencia_2020-09-01_13-21-28_UTC_10mins.h5",
        1789226584,
    )

    assert VALENCIA.file_is_in_time_range(
        remote,
        start=utc("2020-09-01 13:25:00"),
        end=utc("2020-09-01 13:25:01"),
    )
    assert not VALENCIA.file_is_in_time_range(
        remote,
        start=utc("2020-09-01 13:31:28"),
        end=utc("2020-09-01 13:41:28"),
    )


def test_hdf5_block_interval_uses_filename_start_and_ten_minute_duration():
    remote = RemoteFile(
        "/Valencia/Data/SR_Valencia_2020-09-01_13-21-28_UTC/"
        "SR_Valencia_2020-09-01_13-21-28_UTC_10mins.h5",
        1789226584,
    )

    assert VALENCIA.block_interval(remote) == (
        utc("2020-09-01 13:21:28"),
        utc("2020-09-01 13:31:28"),
    )
    assert VALENCIA.block_interval(RemoteFile("/Valencia/readme.txt", 3427)) is None


def test_hour_24_filename_is_normalized_to_the_next_day():
    remote = RemoteFile(
        "/Valencia/Data/SR_Valencia_2020-09-01_24-01-38_UTC/"
        "SR_Valencia_2020-09-01_24-01-38_UTC_10mins.h5",
        1789226584,
    )

    assert VALENCIA.block_interval(remote) == (
        utc("2020-09-02 00:01:38"),
        utc("2020-09-02 00:11:38"),
    )


def test_continuous_intervals_merge_adjacent_blocks_and_keep_gaps():
    files = [
        RemoteFile(
            "/Valencia/Data/SR_Valencia_2020-09-01_13-21-28_UTC/"
            "SR_Valencia_2020-09-01_13-31-28_UTC_10mins.h5",
            1789226584,
        ),
        RemoteFile(
            "/Valencia/Data/SR_Valencia_2020-09-01_13-21-28_UTC/"
            "SR_Valencia_2020-09-01_13-21-28_UTC_10mins.h5",
            1789226584,
        ),
        RemoteFile(
            "/Valencia/Data/SR_Valencia_2020-09-02_09-21-48_UTC/"
            "SR_Valencia_2020-09-02_09-21-48_UTC_10mins.h5",
            1789226584,
        ),
    ]

    assert VALENCIA.continuous_intervals(files) == [
        (utc("2020-09-01 13:21:28"), utc("2020-09-01 13:41:28")),
        (utc("2020-09-02 09:21:48"), utc("2020-09-02 09:31:48")),
    ]


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/Valencia/readme.txt", 3427)

    assert not VALENCIA.file_is_in_time_range(
        remote,
        start=utc("2020-09-01 00:00:00"),
        end=utc("2020-09-02 00:00:00"),
    )


def test_hourly_directory_pruning_uses_one_hour_block_span():
    requested = {
        "start": utc("2020-09-01 13:00:00"),
        "end": utc("2020-09-01 14:00:00"),
    }

    assert VALENCIA.directory_may_overlap_time_range(
        "/Valencia/Data/SR_Valencia_2020-09-01_13-21-28_UTC/",
        **requested,
    )
    assert VALENCIA.directory_may_overlap_time_range(
        "/Valencia/Data/SR_Valencia_2020-09-01_12-21-27_UTC/",
        **requested,
    )
    assert not VALENCIA.directory_may_overlap_time_range(
        "/Valencia/Data/SR_Valencia_2020-09-01_10-21-25_UTC/",
        **requested,
    )
    assert VALENCIA.directory_may_overlap_time_range(
        "/Valencia/Data/",
        **requested,
    )
