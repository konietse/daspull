from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

FOSSA = DATASETS["fossa"]


def test_tdms_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/FOSSA/Data/westSac_170906155429.tdms",
        699457536,
    )

    assert FOSSA.file_is_in_time_range(
        remote,
        start=utc("2017-09-06 15:55:00"),
        end=utc("2017-09-06 15:55:01"),
    )
    assert not FOSSA.file_is_in_time_range(
        remote,
        start=utc("2017-09-06 15:56:00"),
        end=utc("2017-09-06 16:00:00"),
    )


def test_tdms_block_interval_uses_filename_start_and_one_minute_duration():
    remote = RemoteFile(
        "/FOSSA/Data/westSac_170906155429.tdms",
        699457536,
    )

    assert FOSSA.block_interval(remote) == (
        utc("2017-09-06 15:54:29"),
        utc("2017-09-06 15:55:29"),
    )
    assert FOSSA.block_interval(RemoteFile("/FOSSA/readme.txt", 1)) is None


def test_continuous_intervals_merge_adjacent_blocks_and_keep_gaps():
    files = [
        RemoteFile("/FOSSA/Data/westSac_170906155529.tdms", 699457536),
        RemoteFile("/FOSSA/Data/westSac_170906155429.tdms", 699457536),
        RemoteFile("/FOSSA/Data/westSac_170906164029.tdms", 699457536),
    ]

    assert FOSSA.continuous_intervals(files) == [
        (utc("2017-09-06 15:54:29"), utc("2017-09-06 15:56:29")),
        (utc("2017-09-06 16:40:29"), utc("2017-09-06 16:41:29")),
    ]


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/FOSSA/DASchanmap_westsac_2017.csv", 268550)

    assert not FOSSA.file_is_in_time_range(
        remote,
        start=utc("2017-09-06 00:00:00"),
        end=utc("2017-09-13 00:00:00"),
    )


def test_directory_pruning_is_a_no_op_for_flat_fossa_layout():
    requested = {
        "start": utc("2017-09-06 00:00:00"),
        "end": utc("2017-09-13 00:00:00"),
    }

    assert not FOSSA.directories
    assert FOSSA.directory_may_overlap_time_range("/FOSSA/Data/", **requested)
    assert FOSSA.directory_may_overlap_time_range("/FOSSA/", **requested)
    assert FOSSA.directory_may_overlap_time_range(
        "/FOSSA/Data/some/unexpected/subdir/", **requested
    )
