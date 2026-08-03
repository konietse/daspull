from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS

GORDAS_2 = DATASETS["gordas_2"]


def test_block_interval_assumes_the_longest_observed_window():
    # The filename gives the window's start exactly; its length is not encoded
    # anywhere and is either 120 s or 420 s, so the longer one is assumed so a
    # query can never miss a file (see the config's known_issues).
    remote = RemoteFile("/GorDAS-2/20221223T043657Z.h5", 688706231)

    assert GORDAS_2.block_interval(remote) == (
        utc("2022-12-23 04:36:57"),
        utc("2022-12-23 04:43:57"),
    )


def test_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile("/GorDAS-2/20221223T043657Z.h5", 688706231)

    assert GORDAS_2.file_is_in_time_range(
        remote,
        start=utc("2022-12-23 04:40:00"),
        end=utc("2022-12-23 04:40:01"),
    )
    assert not GORDAS_2.file_is_in_time_range(
        remote,
        start=utc("2022-12-23 04:43:57"),
        end=utc("2022-12-23 04:44:57"),
    )


def test_a_files_size_does_not_change_its_interval():
    # Files are gzip-compressed inside the HDF5 container, so size carries no
    # usable duration signal -- a 57 MB and a 777 MB window get the same rule.
    small = RemoteFile("/GorDAS-2/20230424T112728Z.h5", 57369239)
    large = RemoteFile("/GorDAS-2/20230424T112728Z.h5", 777064321)

    assert GORDAS_2.block_interval(small) == GORDAS_2.block_interval(large)


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile("/GorDAS-2/labels.txt", 12920)

    assert not GORDAS_2.file_is_in_time_range(
        remote,
        start=utc("2022-12-01 00:00:00"),
        end=utc("2025-01-01 00:00:00"),
    )
    assert GORDAS_2.block_interval(remote) is None


def test_continuous_intervals_treat_separate_events_as_separate_coverage():
    files = [
        RemoteFile("/GorDAS-2/20221223T085557Z.h5", 667596272),
        RemoteFile("/GorDAS-2/20221223T043657Z.h5", 688706231),
        # 9 minutes after the 08:55:57 window's start, so even the assumed
        # 7-minute length leaves a 2-minute gap between the two
        RemoteFile("/GorDAS-2/20221223T090457Z.h5", 666041818),
    ]

    assert GORDAS_2.continuous_intervals(files) == [
        (utc("2022-12-23 04:36:57"), utc("2022-12-23 04:43:57")),
        (utc("2022-12-23 08:55:57"), utc("2022-12-23 09:02:57")),
        (utc("2022-12-23 09:04:57"), utc("2022-12-23 09:11:57")),
    ]


def test_no_directory_pruning_rules_are_configured():
    assert not GORDAS_2.directories
    assert GORDAS_2.directory_may_overlap_time_range(
        "/GorDAS-2/",
        start=utc("2022-12-01 00:00:00"),
        end=utc("2025-01-01 00:00:00"),
    )


def test_two_acquisition_configurations_are_declared():
    assert [config.sampling_rate_hz for config in GORDAS_2.configurations] == [125, 100]
    assert [config.number_of_channels for config in GORDAS_2.configurations] == [
        7550,
        3020,
    ]


def test_files_are_attributed_to_the_configuration_in_effect():
    # last 2.0419 m file and first 5.1048 m file, from the live catalog
    early = RemoteFile("/GorDAS-2/20230202T221315Z.h5", 209217753)
    late = RemoteFile("/GorDAS-2/20230203T004204Z.h5", 57369239)
    fine, coarse = GORDAS_2.configurations

    assert GORDAS_2.file_used_configurations(early, [fine])
    assert not GORDAS_2.file_used_configurations(early, [coarse])
    assert GORDAS_2.file_used_configurations(late, [coarse])
    assert not GORDAS_2.file_used_configurations(late, [fine])


def test_an_untimestamped_file_survives_any_acquisition_selection():
    remote = RemoteFile("/GorDAS-2/labels.txt", 12920)

    for config in GORDAS_2.configurations:
        assert GORDAS_2.file_used_configurations(remote, [config])


def test_selecting_by_sampling_rate_resolves_one_configuration():
    picked = GORDAS_2.acquisition_configs(sampling_rate=125)

    assert len(picked) == 1
    assert picked[0].channel_spacing_m == 2.0419
