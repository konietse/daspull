from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

DAS4WHALE = DATASETS["das4whale"]


def test_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/DAS4Whale/20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat",
        1033292856,
    )

    assert DAS4WHALE.file_is_in_time_range(
        remote,
        start=utc("2020-06-27 05:25:00"),
        end=utc("2020-06-27 05:25:01"),
    )
    assert not DAS4WHALE.file_is_in_time_range(
        remote,
        start=utc("2020-06-27 05:30:00"),
        end=utc("2020-06-27 05:31:00"),
    )


def test_block_duration_is_read_from_the_filename_and_varies_per_file():
    short = RemoteFile(
        "/DAS4Whale/20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat",
        1033292856,
    )
    medium = RemoteFile(
        "/DAS4Whale/20200627_192255_ch05001_to_ch07000_whale_raw_L310s.mat",
        3201638976,
    )
    long = RemoteFile(
        "/DAS4Whale/20200716_154302_ch24001_to_ch25000_whale_raw_L720s.mat",
        3719802920,
    )

    assert DAS4WHALE.block_interval(short) == (
        utc("2020-06-27 05:24:41"),
        utc("2020-06-27 05:27:21"),
    )
    assert DAS4WHALE.block_interval(medium) == (
        utc("2020-06-27 19:22:55"),
        utc("2020-06-27 19:28:05"),
    )
    assert DAS4WHALE.block_interval(long) == (
        utc("2020-07-16 15:43:02"),
        utc("2020-07-16 15:55:02"),
    )


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/DAS4Whale/some_readme.txt", 100)

    assert not DAS4WHALE.file_is_in_time_range(
        remote,
        start=utc("2020-06-01 00:00:00"),
        end=utc("2020-08-01 00:00:00"),
    )
    assert DAS4WHALE.block_interval(remote) is None


def test_continuous_intervals_merge_files_sharing_a_recording_window():
    files = [
        RemoteFile(
            "/DAS4Whale/20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat",
            1033292856,
        ),
        RemoteFile(
            "/DAS4Whale/20200627_052441_ch10001_to_ch15000_whale_raw_L160s.mat",
            4129952856,
        ),
        RemoteFile(
            "/DAS4Whale/20200627_192255_ch05001_to_ch07000_whale_raw_L310s.mat",
            3201638976,
        ),
    ]

    assert DAS4WHALE.continuous_intervals(files) == [
        (utc("2020-06-27 05:24:41"), utc("2020-06-27 05:27:21")),
        (utc("2020-06-27 19:22:55"), utc("2020-06-27 19:28:05")),
    ]


def test_no_directory_pruning_rules_are_configured():
    assert not DAS4WHALE.directories
    assert DAS4WHALE.directory_may_overlap_time_range(
        "/DAS4Whale/",
        start=utc("2020-06-01 00:00:00"),
        end=utc("2020-08-01 00:00:00"),
    )
