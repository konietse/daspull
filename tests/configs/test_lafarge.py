from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

LAFARGE = DATASETS["lafarge"]


def test_sgy_block_interval_uses_filename_start_and_size_derived_duration():
    # A standard 30 s block: 1120 channels x 30,000 samples x 4 bytes,
    # plus 240-byte trace headers and the 3600-byte SEG-Y file header.
    remote = RemoteFile(
        "/LaFargeConcoMine/Data/Blast2/Blast 2_170728202848.sgy",
        134672400,
    )

    assert LAFARGE.block_interval(remote) == (
        utc("2017-07-28 20:28:48"),
        utc("2017-07-28 20:29:18"),
    )


def test_sgy_block_interval_derives_60s_duration_for_blast1():
    # Blast 1 uses 60 s blocks (60,000 samples), double the byte size of a
    # standard 30 s block.
    remote = RemoteFile(
        "/LaFargeConcoMine/Data/Blast1/Blast 1_170727203539.sgy",
        269072400,
    )

    assert LAFARGE.block_interval(remote) == (
        utc("2017-07-27 20:35:39"),
        utc("2017-07-27 20:36:39"),
    )


def test_sgy_block_interval_derives_partial_final_block_duration():
    # The last file of a run is a shorter, partial block whose duration
    # (49.614 s here) must come from its size rather than a fixed constant.
    remote = RemoteFile(
        "/LaFargeConcoMine/Data/Blast1/Blast 1_170727205239.sgy",
        222543120,
    )

    assert LAFARGE.block_interval(remote) == (
        utc("2017-07-27 20:52:39"),
        utc("2017-07-27 20:53:28.614"),
    )


def test_sgy_block_interval_returns_none_for_files_without_a_timestamp():
    assert (
        LAFARGE.block_interval(RemoteFile("/LaFargeConcoMine/readme.pdf", 610127))
        is None
    )
    assert (
        LAFARGE.block_interval(
            RemoteFile("/LaFargeConcoMine/LaFarge_total_station_survey.xls", 138752)
        )
        is None
    )


def test_sgy_block_interval_returns_none_when_the_size_is_not_a_whole_block():
    # A timestamped name is not enough: a size that does not decompose into
    # whole traces cannot yield a duration, so the file is not time-selected.
    remote = RemoteFile(
        "/LaFargeConcoMine/Data/Blast2/Blast 2_170728202848.sgy",
        134672401,
    )

    assert LAFARGE.block_interval(remote) is None
    assert not LAFARGE.file_is_in_time_range(
        remote,
        start=utc("2017-07-28 20:29:00"),
        end=utc("2017-07-28 20:29:01"),
    )


def test_file_is_in_time_range_uses_the_derived_block_interval():
    remote = RemoteFile(
        "/LaFargeConcoMine/Data/Blast2/Blast 2_170728202848.sgy",
        134672400,
    )

    assert LAFARGE.file_is_in_time_range(
        remote,
        start=utc("2017-07-28 20:29:00"),
        end=utc("2017-07-28 20:29:01"),
    )
    assert not LAFARGE.file_is_in_time_range(
        remote,
        start=utc("2017-07-28 20:30:00"),
        end=utc("2017-07-28 20:40:00"),
    )


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile(
        "/LaFargeConcoMine/UWLafargeReportSEP17_2017_PubDAS.pdf", 2485894
    )

    assert not LAFARGE.file_is_in_time_range(
        remote,
        start=utc("2017-07-27 00:00:00"),
        end=utc("2017-07-29 00:00:00"),
    )


def test_continuous_intervals_merge_adjacent_blocks_and_keep_gaps():
    files = [
        RemoteFile(
            "/LaFargeConcoMine/Data/Blast2/Blast 2_170728202918.sgy",
            134672400,
        ),
        RemoteFile(
            "/LaFargeConcoMine/Data/Blast2/Blast 2_170728202848.sgy",
            134672400,
        ),
        RemoteFile(
            "/LaFargeConcoMine/Data/MiniVibe/MV B_170728185040.sgy",
            134672400,
        ),
    ]

    assert LAFARGE.continuous_intervals(files) == [
        (utc("2017-07-28 18:50:40"), utc("2017-07-28 18:51:10")),
        (utc("2017-07-28 20:28:48"), utc("2017-07-28 20:29:48")),
    ]


def test_directory_may_overlap_time_range_never_prunes():
    requested = {
        "start": utc("2017-07-27 00:00:00"),
        "end": utc("2017-07-28 00:00:00"),
    }

    assert not LAFARGE.directories
    assert LAFARGE.directory_may_overlap_time_range(
        "/LaFargeConcoMine/Data/Blast1/", **requested
    )
    assert LAFARGE.directory_may_overlap_time_range(
        "/LaFargeConcoMine/Data/Blast2/", **requested
    )
    assert LAFARGE.directory_may_overlap_time_range(
        "/LaFargeConcoMine/Data/ESS/B/", **requested
    )
    assert LAFARGE.directory_may_overlap_time_range(
        "/LaFargeConcoMine/Data/", **requested
    )
