from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

STANFORD_1 = DATASETS["stanford_1"]


def test_sgy_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/Stanford-1-Campus/Data/2016/09/03/cbt_processed_20160903_000054.932+0000.sgy",
        7665840,
    )

    assert STANFORD_1.file_is_in_time_range(
        remote,
        start=utc("2016-09-03 00:01:00"),
        end=utc("2016-09-03 00:01:01"),
    )
    assert not STANFORD_1.file_is_in_time_range(
        remote,
        start=utc("2016-09-03 00:02:00"),
        end=utc("2016-09-03 00:03:00"),
    )


def test_sgy_block_interval_uses_filename_start_and_sixty_second_duration():
    remote = RemoteFile(
        "/Stanford-1-Campus/Data/2016/09/03/cbt_processed_20160903_000054.932+0000.sgy",
        7665840,
    )

    assert STANFORD_1.block_interval(remote) == (
        utc("2016-09-03 00:00:54"),
        utc("2016-09-03 00:01:54"),
    )
    assert (
        STANFORD_1.block_interval(RemoteFile("/Stanford-1-Campus/readme.txt", 5575))
        is None
    )


def test_continuous_intervals_merge_adjacent_blocks_and_keep_gaps():
    files = [
        RemoteFile(
            "/Stanford-1-Campus/Data/2016/09/03/"
            "cbt_processed_20160903_000154.932+0000.sgy",
            7665840,
        ),
        RemoteFile(
            "/Stanford-1-Campus/Data/2016/09/03/"
            "cbt_processed_20160903_000054.932+0000.sgy",
            7665840,
        ),
        RemoteFile(
            "/Stanford-1-Campus/Data/2016/09/03/"
            "cbt_processed_20160903_235954.932+0000.sgy",
            7665840,
        ),
    ]

    assert STANFORD_1.continuous_intervals(files) == [
        (utc("2016-09-03 00:00:54"), utc("2016-09-03 00:02:54")),
        (utc("2016-09-03 23:59:54"), utc("2016-09-04 00:00:54")),
    ]


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile(
        "/Stanford-1-Campus/Data/BK_JRSC/"
        "BK.JRSC.00.HHE__20160901T000000Z__20160902T000000Z.mseed",
        9322496,
    )

    assert not STANFORD_1.file_is_in_time_range(
        remote,
        start=utc("2016-09-01 00:00:00"),
        end=utc("2016-09-02 00:00:00"),
    )


def test_daily_directory_pruning_uses_utc_calendar_day():
    requested = {
        "start": utc("2016-09-03 00:00:00"),
        "end": utc("2016-09-04 00:00:00"),
    }

    assert STANFORD_1.directory_may_overlap_time_range(
        "/Stanford-1-Campus/Data/2016/09/03/",
        **requested,
    )
    assert not STANFORD_1.directory_may_overlap_time_range(
        "/Stanford-1-Campus/Data/2016/09/04/",
        **requested,
    )
    assert STANFORD_1.directory_may_overlap_time_range(
        "/Stanford-1-Campus/Data/2016/09/",
        **requested,
    )
    assert not STANFORD_1.directory_may_overlap_time_range(
        "/Stanford-1-Campus/Data/2016/10/",
        **requested,
    )
    assert STANFORD_1.directory_may_overlap_time_range(
        "/Stanford-1-Campus/Data/2016/",
        **requested,
    )
    assert not STANFORD_1.directory_may_overlap_time_range(
        "/Stanford-1-Campus/Data/2019/",
        **requested,
    )
    assert STANFORD_1.directory_may_overlap_time_range(
        "/Stanford-1-Campus/Data/",
        **requested,
    )
    assert STANFORD_1.directory_may_overlap_time_range(
        "/Stanford-1-Campus/Data/BK_JRSC/",
        **requested,
    )
