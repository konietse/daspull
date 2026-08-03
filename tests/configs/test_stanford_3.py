import pytest
from helpers import utc

from daspull.catalog import RemoteFile
from daspull.datasets import DATASETS
from daspull.datasets.acquisition import AcquisitionSelectionError

STANFORD_3 = DATASETS["stanford_3"]


def test_segy_block_is_selected_when_it_overlaps_interval():
    remote = RemoteFile(
        "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/SGY_Stanford_Permanent_DT37/"
        "cbt_processed_20171006_223449.533+0000.sgy",
        18738240,
    )

    assert STANFORD_3.file_is_in_time_range(
        remote,
        start=utc("2017-10-06 22:36:00.000"),
        end=utc("2017-10-06 22:36:01.000"),
    )
    assert not STANFORD_3.file_is_in_time_range(
        remote,
        start=utc("2017-10-06 22:40:00.000"),
        end=utc("2017-10-06 22:45:00.000"),
    )


def test_segy_block_interval_uses_filename_start_and_five_minute_duration():
    remote = RemoteFile(
        "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/SGY_Stanford_Permanent_DT37/"
        "cbt_processed_20171006_223449.533+0000.sgy",
        18738240,
    )

    assert STANFORD_3.block_interval(remote) == (
        utc("2017-10-06 22:34:49.533"),
        utc("2017-10-06 22:39:49.533"),
    )
    assert (
        STANFORD_3.block_interval(RemoteFile("/Stanford-3-ODH4/readme.txt", 1)) is None
    )


def test_continuous_intervals_merge_adjacent_blocks_and_keep_gaps():
    files = [
        RemoteFile(
            "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/SGY_Stanford_Permanent_DT37/"
            "cbt_processed_20171006_223949.533+0000.sgy",
            100,
        ),
        RemoteFile(
            "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/SGY_Stanford_Permanent_DT37/"
            "cbt_processed_20171006_223449.533+0000.sgy",
            100,
        ),
        RemoteFile(
            "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/"
            "SGY_Stanford_Permanent_DT37_100_Hz_2m_gauge/"
            "cbt_processed_20171010_183035.513+0000.sgy",
            100,
        ),
    ]

    assert STANFORD_3.continuous_intervals(files) == [
        (utc("2017-10-06 22:34:49.533"), utc("2017-10-06 22:44:49.533")),
        (utc("2017-10-10 18:30:35.513"), utc("2017-10-10 18:35:35.513")),
    ]


def test_time_range_excludes_files_without_timestamp():
    remote = RemoteFile(
        "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/"
        "ODH4-Stanford_DAS_Array_Operational_Log.xlsx",
        10241,
    )

    assert not STANFORD_3.file_is_in_time_range(
        remote,
        start=utc("2017-10-06 00:00:00.000"),
        end=utc("2017-10-13 00:00:00.000"),
    )


def test_directory_pruning_is_not_supported_and_always_true():
    requested = {
        "start": utc("2017-10-06 00:00:00.000"),
        "end": utc("2017-10-13 00:00:00.000"),
    }

    assert not STANFORD_3.directories
    assert STANFORD_3.directory_may_overlap_time_range(
        "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/SGY_Stanford_Permanent_DT37/",
        **requested,
    )
    assert STANFORD_3.directory_may_overlap_time_range(
        "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/"
        "SGY_Stanford_Permanent_DT37_100Hz_4m_Gauge/",
        **requested,
    )


SGY = "/Stanford-3-ODH4/Data/ODH4-2017-SEGY"


def test_five_acquisition_configurations_are_declared():
    rates = [config.sampling_rate_hz for config in STANFORD_3.configurations]

    assert rates == [50, 100, 100, 100, 100]
    assert [config.gauge_length_m for config in STANFORD_3.configurations] == [
        7.14,
        7.14,
        2,
        7.14,
        4,
    ]


def test_each_configuration_claims_only_its_own_subtree():
    fifty = STANFORD_3.acquisition_configs(sampling_rate=50)
    block = RemoteFile(
        f"{SGY}/SGY_Stanford_Permanent_DT37/cbt_processed_20171006_223449.533+0000.sgy",
        18738240,
    )
    other = RemoteFile(
        f"{SGY}/SGY_Stanford_Permanent_DT37_100Hz/cbt_processed_20171009_175814.479+0000.sgy",
        37398240,
    )

    assert STANFORD_3.file_used_configurations(block, fifty)
    assert not STANFORD_3.file_used_configurations(other, fifty)


def test_a_sampling_rate_shared_by_differing_gauges_still_needs_narrowing():
    with pytest.raises(AcquisitionSelectionError, match="still spans 3"):
        STANFORD_3.acquisition_configs(sampling_rate=100)


def test_a_sampling_rate_and_gauge_shared_only_by_a_duplicate_run_is_not_ambiguous():
    hundred = STANFORD_3.acquisition_configs(sampling_rate=100, gauge_length=7.14)

    assert len(hundred) == 2


def test_the_gauge_length_of_the_default_runs_cannot_be_selected():
    two_metre = STANFORD_3.acquisition_configs(gauge_length=2)

    assert len(two_metre) == 1
    assert two_metre[0].root.endswith("SGY_Stanford_Permanent_DT37_100_Hz_2m_gauge/")


def test_subtree_pruning_skips_the_other_configurations():
    four_metre = STANFORD_3.acquisition_configs(gauge_length=4)

    assert STANFORD_3.directory_may_hold_configurations(f"{SGY}/", four_metre)
    assert STANFORD_3.directory_may_hold_configurations(
        f"{SGY}/SGY_Stanford_Permanent_DT37_100Hz_4m_Gauge/", four_metre
    )
    assert not STANFORD_3.directory_may_hold_configurations(
        f"{SGY}/SGY_Stanford_Permanent_DT37/", four_metre
    )
