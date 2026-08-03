from datetime import datetime, timezone

import pytest

from daspull.datasets.acquisition import (
    AcquisitionConfig,
    AcquisitionSelectionError,
    acquisition_configs,
    select_configs,
)

UTC = timezone.utc

FLAT = {
    "sampling_rate_hz": 1000,
    "channel_spacing_m": 1,
    "gauge_length_m": 10,
    "number_of_channels": 1000,
}

TWO_EPOCHS = {
    "configurations": [
        {
            "sampling_rate_hz": 125,
            "channel_spacing_m": 2.0419,
            "gauge_length_m": 8.1676,
            "number_of_channels": 7550,
            "end": "2023-02-03 00:00:00",
        },
        {
            "sampling_rate_hz": 100,
            "channel_spacing_m": 5.1048,
            "gauge_length_m": 8.1676,
            "number_of_channels": 3020,
            "start": "2023-02-03 00:00:00",
        },
    ]
}

TWO_SUBTREES = {
    "configurations": [
        {
            "sampling_rate_hz": 50,
            "channel_spacing_m": 8.16,
            "gauge_length_m": None,
            "root": "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/SGY_A/",
        },
        {
            "sampling_rate_hz": 100,
            "channel_spacing_m": 8.16,
            "gauge_length_m": 2,
            "root": "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/SGY_A_2m_gauge/",
        },
    ]
}


def test_a_flat_section_becomes_one_configuration():
    configs = acquisition_configs(FLAT)

    assert len(configs) == 1
    assert configs[0].sampling_rate_hz == 1000
    assert configs[0].is_whole_dataset


def test_a_declared_list_becomes_one_configuration_each():
    configs = acquisition_configs(TWO_EPOCHS)

    assert [config.sampling_rate_hz for config in configs] == [125, 100]
    assert configs[0].end == datetime(2023, 2, 3, tzinfo=UTC)
    assert configs[0].start is None
    assert not configs[0].is_whole_dataset


def test_a_single_configuration_needs_no_selection():
    configs = acquisition_configs(FLAT)

    assert select_configs(configs) == configs


def test_several_configurations_refuse_an_unspecified_selection():
    configs = acquisition_configs(TWO_EPOCHS)

    with pytest.raises(AcquisitionSelectionError, match="2 different acquisition"):
        select_configs(configs, dataset="GorDAS-2")


def test_a_value_picks_the_matching_configuration():
    configs = acquisition_configs(TWO_EPOCHS)

    picked = select_configs(configs, sampling_rate=125)

    assert len(picked) == 1
    assert picked[0].number_of_channels == 7550


def test_a_rounded_value_still_matches():
    configs = acquisition_configs(TWO_EPOCHS)

    assert select_configs(configs, channel_spacing=5.1)[0].sampling_rate_hz == 100


def test_a_value_off_by_more_than_the_tolerance_does_not_match():
    configs = acquisition_configs(TWO_EPOCHS)

    with pytest.raises(AcquisitionSelectionError, match="no .* has channel spacing 2"):
        select_configs(configs, channel_spacing=2)


def test_several_values_must_agree_on_one_configuration():
    configs = acquisition_configs(TWO_EPOCHS)

    with pytest.raises(AcquisitionSelectionError, match="sampling rate 125"):
        select_configs(configs, sampling_rate=125, channel_spacing=5.1048)


def test_a_value_shared_by_differing_configurations_still_needs_narrowing():
    configs = acquisition_configs(TWO_EPOCHS)

    with pytest.raises(AcquisitionSelectionError, match="still spans 2"):
        select_configs(configs, gauge_length=8.1676)


def test_a_value_shared_only_by_identically_settled_configurations_is_not_ambiguous():
    identical_pair = (
        AcquisitionConfig(
            sampling_rate_hz=100,
            channel_spacing_m=8.16,
            gauge_length_m=7.14,
            root="/A/",
        ),
        AcquisitionConfig(
            sampling_rate_hz=100,
            channel_spacing_m=8.16,
            gauge_length_m=7.14,
            root="/B/",
        ),
    )

    assert len(select_configs(identical_pair, sampling_rate=100)) == 2


def test_a_setting_no_configuration_publishes_is_reported_as_such():
    configs = acquisition_configs(
        {"sampling_rate_hz": 2000, "channel_spacing_m": None, "gauge_length_m": None}
    )

    with pytest.raises(AcquisitionSelectionError, match="not published"):
        select_configs(configs, channel_spacing=1, dataset="FORGE Phase 2C")


def test_a_value_validates_against_a_single_configuration():
    configs = acquisition_configs(FLAT)

    with pytest.raises(AcquisitionSelectionError, match="no Fairbanks"):
        select_configs(configs, sampling_rate=500, dataset="Fairbanks")


def test_a_time_bounded_configuration_covers_blocks_that_began_inside_it():
    early, late = acquisition_configs(TWO_EPOCHS)
    before = (datetime(2023, 2, 2, 22, 13, 15, tzinfo=UTC),) * 2
    after = (datetime(2023, 2, 3, 0, 42, 4, tzinfo=UTC),) * 2

    assert early.covers("/GorDAS-2/x.h5", before)
    assert not early.covers("/GorDAS-2/x.h5", after)
    assert late.covers("/GorDAS-2/x.h5", after)
    assert not late.covers("/GorDAS-2/x.h5", before)


def test_a_block_is_attributed_by_its_start_not_its_end():
    early, late = acquisition_configs(TWO_EPOCHS)
    # a block that began before the switch but nominally runs past it
    straddling = (
        datetime(2023, 2, 2, 23, 58, tzinfo=UTC),
        datetime(2023, 2, 3, 0, 5, tzinfo=UTC),
    )

    assert early.covers("/GorDAS-2/x.h5", straddling)
    assert not late.covers("/GorDAS-2/x.h5", straddling)


def test_an_untimestamped_file_belongs_to_no_time_bounded_configuration():
    early, late = acquisition_configs(TWO_EPOCHS)

    assert not early.covers("/GorDAS-2/readme.txt", None)
    assert not late.covers("/GorDAS-2/readme.txt", None)


def test_a_subtree_configuration_covers_only_its_own_subtree():
    fifty, hundred = acquisition_configs(TWO_SUBTREES)
    root = "/Stanford-3-ODH4/Data/ODH4-2017-SEGY"

    assert fifty.covers(f"{root}/SGY_A/block.sgy", None)
    # a sibling directory whose name merely starts the same must not match
    assert not fifty.covers(f"{root}/SGY_A_2m_gauge/block.sgy", None)
    assert hundred.covers(f"{root}/SGY_A_2m_gauge/block.sgy", None)


def test_a_subtree_configuration_prunes_unrelated_directories():
    fifty, _ = acquisition_configs(TWO_SUBTREES)

    assert fifty.may_hold_directory("/Stanford-3-ODH4/Data/ODH4-2017-SEGY/")
    assert fifty.may_hold_directory(
        "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/SGY_A/nested/"
    )
    assert not fifty.may_hold_directory(
        "/Stanford-3-ODH4/Data/ODH4-2017-SEGY/SGY_A_2m_gauge/"
    )


def test_a_configuration_describes_itself_with_the_values_it_has():
    described = AcquisitionConfig(
        sampling_rate_hz=100,
        channel_spacing_m=8.16,
        gauge_length_m=None,
        root="/Stanford-3-ODH4/Data/ODH4-2017-SEGY/SGY_A/",
    ).describe()

    assert described == "100 Hz, 8.16 m spacing  [SGY_A/]"
