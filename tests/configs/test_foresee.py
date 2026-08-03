from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

FORESEE = DATASETS["foresee"]


def test_hdf5_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/FORESEE/Data/201904/FORESEE_UTC_20190404_194804.hdf5",
        321152048,
    )

    assert FORESEE.file_is_in_time_range(
        remote,
        start=utc("2019-04-04 19:50:00"),
        end=utc("2019-04-04 19:50:01"),
    )
    assert not FORESEE.file_is_in_time_range(
        remote,
        start=utc("2019-04-04 20:00:00"),
        end=utc("2019-04-04 20:10:00"),
    )


def test_hdf5_block_interval_uses_filename_start_and_ten_minute_duration():
    remote = RemoteFile(
        "/FORESEE/Data/201904/FORESEE_UTC_20190404_194804.hdf5",
        321152048,
    )

    assert FORESEE.block_interval(remote) == (
        utc("2019-04-04 19:48:04"),
        utc("2019-04-04 19:58:04"),
    )
    assert FORESEE.block_interval(RemoteFile("/FORESEE/readme.txt", 1)) is None


def test_continuous_hdf5_intervals_merge_adjacent_blocks_and_keep_gaps():
    files = [
        RemoteFile("/FORESEE/Data/201904/FORESEE_UTC_20190404_195804.hdf5", 100),
        RemoteFile("/FORESEE/Data/201904/FORESEE_UTC_20190404_194804.hdf5", 100),
        RemoteFile("/FORESEE/Data/201904/FORESEE_UTC_20190405_185804.hdf5", 100),
    ]

    assert FORESEE.continuous_intervals(files) == [
        (utc("2019-04-04 19:48:04"), utc("2019-04-04 20:08:04")),
        (utc("2019-04-05 18:58:04"), utc("2019-04-05 19:08:04")),
    ]


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/FORESEE/readme.txt", 3245)

    assert not FORESEE.file_is_in_time_range(
        remote,
        start=utc("2019-04-04 00:00:00"),
        end=utc("2019-04-05 00:00:00"),
    )


def test_monthly_directory_pruning_uses_utc_calendar_month():
    requested = {
        "start": utc("2019-04-05 00:00:00"),
        "end": utc("2019-05-05 00:00:00"),
    }

    assert FORESEE.directory_may_overlap_time_range(
        "/FORESEE/Data/201904/",
        **requested,
    )
    assert FORESEE.directory_may_overlap_time_range(
        "/FORESEE/Data/201905/",
        **requested,
    )
    assert not FORESEE.directory_may_overlap_time_range(
        "/FORESEE/Data/201906/",
        **requested,
    )
    assert FORESEE.directory_may_overlap_time_range(
        "/FORESEE/Data/",
        **requested,
    )


def test_december_directory_span_rolls_over_into_the_next_year():
    assert FORESEE.directory_may_overlap_time_range(
        "/FORESEE/Data/201912/",
        start=utc("2019-12-31 23:00:00"),
        end=utc("2020-01-02 00:00:00"),
    )
    assert not FORESEE.directory_may_overlap_time_range(
        "/FORESEE/Data/201912/",
        start=utc("2020-01-01 00:00:00"),
        end=utc("2020-01-02 00:00:00"),
    )
