from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

POROTOMO_V = DATASETS["porotomo_v"]


def test_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/PoroTomo_V/20160317/PoroTomo_iDAS025_160318160317.h5", 46344096
    )

    assert POROTOMO_V.file_is_in_time_range(
        remote,
        start=utc("2016-03-18 16:03:30"),
        end=utc("2016-03-18 16:03:31"),
    )
    assert not POROTOMO_V.file_is_in_time_range(
        remote,
        start=utc("2016-03-18 16:04:00"),
        end=utc("2016-03-18 16:05:00"),
    )


def test_block_interval_uses_filename_start_and_thirty_second_duration():
    # The 20160317/ folder itself only holds two files timestamped 2016-03-18
    # (setup/leftover files); this is not a bug in the block rule.
    remote = RemoteFile(
        "/PoroTomo_V/20160317/PoroTomo_iDAS025_160318160317.h5", 46344096
    )

    assert POROTOMO_V.block_interval(remote) == (
        utc("2016-03-18 16:03:17"),
        utc("2016-03-18 16:03:47"),
    )


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/PoroTomo_V/0README.TXT", 200)

    assert not POROTOMO_V.file_is_in_time_range(
        remote,
        start=utc("2016-03-17 00:00:00"),
        end=utc("2016-03-27 00:00:00"),
    )
    assert POROTOMO_V.block_interval(remote) is None


def test_continuous_intervals_merge_adjacent_blocks_and_keep_gaps():
    files = [
        RemoteFile("/PoroTomo_V/20160318/PoroTomo_iDAS025_160318020947.h5", 46344096),
        RemoteFile("/PoroTomo_V/20160318/PoroTomo_iDAS025_160318020917.h5", 46344096),
        RemoteFile("/PoroTomo_V/20160326/PoroTomo_iDAS025_160326120000.h5", 46344096),
    ]

    assert POROTOMO_V.continuous_intervals(files) == [
        (utc("2016-03-18 02:09:17"), utc("2016-03-18 02:10:17")),
        (utc("2016-03-26 12:00:00"), utc("2016-03-26 12:00:30")),
    ]


def test_daily_directory_pruning_uses_utc_calendar_day():
    requested = {
        "start": utc("2016-03-18 00:00:00"),
        "end": utc("2016-03-19 00:00:00"),
    }

    assert POROTOMO_V.directory_may_overlap_time_range(
        "/PoroTomo_V/20160318/", **requested
    )
    assert not POROTOMO_V.directory_may_overlap_time_range(
        "/PoroTomo_V/20160320/", **requested
    )
    assert POROTOMO_V.directory_may_overlap_time_range("/PoroTomo_V/", **requested)
