from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

MARS = DATASETS["mars"]

SIZE = 136566144


def test_block_interval_uses_filename_start_and_sixty_second_duration():
    remote = RemoteFile("/MARS/20220730T233258Z.h5", SIZE)

    assert MARS.block_interval(remote) == (
        utc("2022-07-30 23:32:58"),
        utc("2022-07-30 23:33:58"),
    )


def test_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile("/MARS/20220730T233258Z.h5", SIZE)

    assert MARS.file_is_in_time_range(
        remote,
        start=utc("2022-07-30 23:33:00"),
        end=utc("2022-07-30 23:33:01"),
    )
    assert not MARS.file_is_in_time_range(
        remote,
        start=utc("2022-07-30 23:33:58"),
        end=utc("2022-07-30 23:34:58"),
    )


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/MARS/README.md", 7602)

    assert not MARS.file_is_in_time_range(
        remote,
        start=utc("2022-07-01 00:00:00"),
        end=utc("2025-01-01 00:00:00"),
    )
    assert MARS.block_interval(remote) is None


def test_continuous_intervals_keep_the_excerpts_separate():
    files = [
        RemoteFile("/MARS/20241217T092528Z.h5", SIZE),
        RemoteFile("/MARS/20220730T233258Z.h5", SIZE),
    ]

    assert MARS.continuous_intervals(files) == [
        (utc("2022-07-30 23:32:58"), utc("2022-07-30 23:33:58")),
        (utc("2024-12-17 09:25:28"), utc("2024-12-17 09:26:28")),
    ]


def test_no_directory_pruning_rules_are_configured():
    assert not MARS.directories
    assert MARS.directory_may_overlap_time_range(
        "/MARS/",
        start=utc("2022-07-01 00:00:00"),
        end=utc("2025-01-01 00:00:00"),
    )
