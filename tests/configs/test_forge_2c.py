from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

FORGE_2C = DATASETS["forge_2c"]


def test_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190419001218.sgy", 130824720
    )

    assert FORGE_2C.file_is_in_time_range(
        remote,
        start=utc("2019-04-19 00:12:20"),
        end=utc("2019-04-19 00:12:30"),
    )
    assert not FORGE_2C.file_is_in_time_range(
        remote,
        start=utc("2019-04-19 00:13:00"),
        end=utc("2019-04-19 00:14:00"),
    )


def test_block_duration_is_a_fixed_fifteen_seconds():
    remote = RemoteFile(
        "/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190419001218.sgy", 130824720
    )

    assert FORGE_2C.block_interval(remote) == (
        utc("2019-04-19 00:12:18"),
        utc("2019-04-19 00:12:33"),
    )


def test_block_duration_is_independent_of_file_size():
    # The interrogator's channel count changed at least once during the
    # deployment, so file size alone does not encode block duration here --
    # every block is treated as the same nominal 15 s regardless of size.
    smaller_file = RemoteFile(
        "/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190503131438.sgy", 110902800
    )

    assert FORGE_2C.block_interval(smaller_file) == (
        utc("2019-05-03 13:14:38"),
        utc("2019-05-03 13:14:53"),
    )


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/FORGE_2C/FORGE_DFIT_NAV.csv", 100)

    assert not FORGE_2C.file_is_in_time_range(
        remote,
        start=utc("2019-04-01 00:00:00"),
        end=utc("2019-06-01 00:00:00"),
    )
    assert FORGE_2C.block_interval(remote) is None


def test_continuous_intervals_merge_adjacent_blocks():
    files = [
        RemoteFile("/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190419001218.sgy", 130824720),
        RemoteFile("/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190419001233.sgy", 130824720),
        RemoteFile("/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190419001248.sgy", 130824720),
    ]

    assert FORGE_2C.continuous_intervals(files) == [
        (utc("2019-04-19 00:12:18"), utc("2019-04-19 00:13:03"))
    ]


def test_continuous_intervals_treat_a_gap_as_separate_coverage():
    files = [
        RemoteFile("/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190419001218.sgy", 130824720),
        RemoteFile("/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190503131438.sgy", 110902800),
    ]

    assert FORGE_2C.continuous_intervals(files) == [
        (utc("2019-04-19 00:12:18"), utc("2019-04-19 00:12:33")),
        (utc("2019-05-03 13:14:38"), utc("2019-05-03 13:14:53")),
    ]


def test_no_directory_pruning_rules_are_configured():
    assert not FORGE_2C.directories
    assert FORGE_2C.directory_may_overlap_time_range(
        "/FORGE_2C/",
        start=utc("2019-04-01 00:00:00"),
        end=utc("2019-06-01 00:00:00"),
    )
