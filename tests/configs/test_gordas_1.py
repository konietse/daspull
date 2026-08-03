from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

GORDAS_1 = DATASETS["gordas_1"]

EVENT = "/GorDAS-1/2022-06-03T20:46:03.530Z"
PREFIX = "Eureka-DT1087-2m-P5kHz-fs250Hz"


def block(timestamp, size=169607757):
    return RemoteFile(f"{EVENT}/{PREFIX}_{timestamp}Z.h5", size)


def test_block_interval_uses_filename_start_and_sixty_second_duration():
    remote = block("2022-06-03T204121")

    assert GORDAS_1.block_interval(remote) == (
        utc("2022-06-03 20:41:21"),
        utc("2022-06-03 20:42:21"),
    )


def test_block_is_selected_when_it_overlaps_interval():
    remote = block("2022-06-03T204121")

    assert GORDAS_1.file_is_in_time_range(
        remote,
        start=utc("2022-06-03 20:42:00"),
        end=utc("2022-06-03 20:42:01"),
    )
    assert not GORDAS_1.file_is_in_time_range(
        remote,
        start=utc("2022-06-03 20:42:21"),
        end=utc("2022-06-03 20:43:21"),
    )


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/GorDAS-1/README.md", 7602)

    assert not GORDAS_1.file_is_in_time_range(
        remote,
        start=utc("2022-06-01 00:00:00"),
        end=utc("2022-07-01 00:00:00"),
    )
    assert GORDAS_1.block_interval(remote) is None


def test_continuous_intervals_merge_an_events_minute_blocks():
    files = [
        block("2022-06-03T204221"),
        block("2022-06-03T204121"),
        block("2022-06-03T204321"),
        # a second event days later stays a separate interval
        RemoteFile(
            f"/GorDAS-1/2022-06-05T22:44:37.420Z/{PREFIX}_2022-06-05T223921Z.h5",
            169607757,
        ),
    ]

    assert GORDAS_1.continuous_intervals(files) == [
        (utc("2022-06-03 20:41:21"), utc("2022-06-03 20:44:21")),
        (utc("2022-06-05 22:39:21"), utc("2022-06-05 22:40:21")),
    ]


def test_event_directory_pruning_keeps_a_days_slack_on_each_side():
    requested = {
        "start": utc("2022-06-03 00:00:00"),
        "end": utc("2022-06-04 00:00:00"),
    }

    assert GORDAS_1.directory_may_overlap_time_range(f"{EVENT}/", **requested)
    # 2022-06-04 is inside the padded span of the 06-03 event directory
    assert GORDAS_1.directory_may_overlap_time_range(
        "/GorDAS-1/2022-06-04T00:15:00.000Z/", **requested
    )
    assert not GORDAS_1.directory_may_overlap_time_range(
        "/GorDAS-1/2022-06-30T21:49:07.410Z/", **requested
    )
    assert GORDAS_1.directory_may_overlap_time_range("/GorDAS-1/", **requested)
