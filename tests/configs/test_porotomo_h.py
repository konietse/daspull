from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

POROTOMO_H = DATASETS["porotomo_h"]


def test_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/PoroTomo_H/20160311/PoroTomo_iDAS16043_160311164618.h5", 1046784080
    )

    assert POROTOMO_H.file_is_in_time_range(
        remote,
        start=utc("2016-03-11 16:46:30"),
        end=utc("2016-03-11 16:46:31"),
    )
    assert not POROTOMO_H.file_is_in_time_range(
        remote,
        start=utc("2016-03-11 16:47:00"),
        end=utc("2016-03-11 16:48:00"),
    )


def test_block_interval_uses_filename_start_and_thirty_second_duration():
    remote = RemoteFile(
        "/PoroTomo_H/20160311/PoroTomo_iDAS16043_160311164618.h5", 1046784080
    )

    assert POROTOMO_H.block_interval(remote) == (
        utc("2016-03-11 16:46:18"),
        utc("2016-03-11 16:46:48"),
    )


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/PoroTomo_H/DASH_file_count.txt", 551)

    assert not POROTOMO_H.file_is_in_time_range(
        remote,
        start=utc("2016-03-08 00:00:00"),
        end=utc("2016-03-27 00:00:00"),
    )
    assert POROTOMO_H.block_interval(remote) is None


def test_continuous_intervals_merge_adjacent_blocks_and_keep_gaps():
    files = [
        RemoteFile(
            "/PoroTomo_H/20160311/PoroTomo_iDAS16043_160311164648.h5", 1046784080
        ),
        RemoteFile(
            "/PoroTomo_H/20160311/PoroTomo_iDAS16043_160311164618.h5", 1046784080
        ),
        RemoteFile(
            "/PoroTomo_H/20160312/PoroTomo_iDAS16043_160312000018.h5", 1046784080
        ),
    ]

    assert POROTOMO_H.continuous_intervals(files) == [
        (utc("2016-03-11 16:46:18"), utc("2016-03-11 16:47:18")),
        (utc("2016-03-12 00:00:18"), utc("2016-03-12 00:00:48")),
    ]


def test_daily_directory_pruning_uses_utc_calendar_day():
    requested = {
        "start": utc("2016-03-11 00:00:00"),
        "end": utc("2016-03-12 00:00:00"),
    }

    assert POROTOMO_H.directory_may_overlap_time_range(
        "/PoroTomo_H/20160311/", **requested
    )
    assert not POROTOMO_H.directory_may_overlap_time_range(
        "/PoroTomo_H/20160313/", **requested
    )
    assert POROTOMO_H.directory_may_overlap_time_range("/PoroTomo_H/", **requested)
