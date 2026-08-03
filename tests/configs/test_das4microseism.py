from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

DAS4MICROSEISM = DATASETS["das4microseism"]


def test_hourly_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/DAS4Microseism/Data/Hourly/"
        "20200705_000005_ch01050_to_ch18000_rsamp20ms_L300s_hourly_nogeom.mat",
        366944840,
    )

    assert DAS4MICROSEISM.file_is_in_time_range(
        remote,
        start=utc("2020-07-05 00:02:00"),
        end=utc("2020-07-05 00:02:01"),
    )
    assert not DAS4MICROSEISM.file_is_in_time_range(
        remote,
        start=utc("2020-07-05 01:00:00"),
        end=utc("2020-07-05 02:00:00"),
    )


def test_hourly_block_interval_uses_filename_start_and_five_minute_duration():
    remote = RemoteFile(
        "/DAS4Microseism/Data/Hourly/"
        "20200705_000005_ch01050_to_ch18000_rsamp20ms_L300s_hourly_nogeom.mat",
        366944840,
    )

    assert DAS4MICROSEISM.block_interval(remote) == (
        utc("2020-07-05 00:00:05"),
        utc("2020-07-05 00:05:05"),
    )


def test_example_block_uses_filename_start_and_twenty_minute_duration():
    remote = RemoteFile(
        "/DAS4Microseism/Data/"
        "20200722_060002_ch00001_to_ch03000_rsamp20ms_L1200s_nogeom.mat",
        1440727080,
    )

    assert DAS4MICROSEISM.block_interval(remote) == (
        utc("2020-07-22 06:00:02"),
        utc("2020-07-22 06:20:02"),
    )


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/DAS4Microseism/00_README.txt", 13671)

    assert not DAS4MICROSEISM.file_is_in_time_range(
        remote,
        start=utc("2020-06-23 00:00:00"),
        end=utc("2020-08-04 00:00:00"),
    )
    assert DAS4MICROSEISM.block_interval(remote) is None


def test_continuous_intervals_merge_the_two_adjacent_twenty_minute_blocks():
    files = [
        RemoteFile(
            "/DAS4Microseism/Data/"
            "20200722_060002_ch00001_to_ch03000_rsamp20ms_L1200s_nogeom.mat",
            1440727080,
        ),
        RemoteFile(
            "/DAS4Microseism/Data/"
            "20200722_060002_ch03001_to_ch05000_rsamp20ms_L1200s_nogeom.mat",
            960727080,
        ),
        RemoteFile(
            "/DAS4Microseism/Data/"
            "20200722_062002_ch00001_to_ch03000_rsamp20ms_L1200s_nogeom.mat",
            1440727080,
        ),
    ]

    assert DAS4MICROSEISM.continuous_intervals(files) == [
        (utc("2020-07-22 06:00:02"), utc("2020-07-22 06:40:02")),
    ]


def test_continuous_intervals_keep_the_gap_between_separate_hourly_snapshots():
    files = [
        RemoteFile(
            "/DAS4Microseism/Data/Hourly/"
            "20200705_000005_ch01050_to_ch18000_rsamp20ms_L300s_hourly_nogeom.mat",
            366944840,
        ),
        RemoteFile(
            "/DAS4Microseism/Data/Hourly/"
            "20200705_010004_ch01050_to_ch18000_rsamp20ms_L300s_hourly_nogeom.mat",
            366944840,
        ),
    ]

    assert DAS4MICROSEISM.continuous_intervals(files) == [
        (utc("2020-07-05 00:00:05"), utc("2020-07-05 00:05:05")),
        (utc("2020-07-05 01:00:04"), utc("2020-07-05 01:05:04")),
    ]


def test_no_directory_pruning_rules_are_configured():
    assert not DAS4MICROSEISM.directories
    assert DAS4MICROSEISM.directory_may_overlap_time_range(
        "/DAS4Microseism/Data/Hourly/",
        start=utc("2020-06-23 00:00:00"),
        end=utc("2020-08-04 00:00:00"),
    )
