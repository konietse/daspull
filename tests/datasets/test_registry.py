"""Tests for the config-driven dataset registry itself.

The per-dataset test modules cover each dataset's own timestamp conventions;
these cover the loader and the invariants every config must satisfy.
"""

import json
import re

import pytest

from daspull.datasets import CONFIG_DIR, DATASETS, load_dataset
from daspull.datasets.acquisition import SELECTABLE


def test_every_config_in_the_package_is_registered():
    configs = sorted(path.stem for path in CONFIG_DIR.glob("*.yaml"))

    assert configs == sorted(DATASETS)
    assert len(DATASETS) == 18


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_config_id_matches_its_filename(name):
    assert load_dataset(CONFIG_DIR / f"{name}.yaml").name == name


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_primary_root_sits_inside_the_dataset_root(name):
    dataset = DATASETS[name]

    assert dataset.dataset_root.startswith("/")
    assert dataset.dataset_root.endswith("/")
    assert dataset.primary_root.startswith(dataset.dataset_root)
    assert dataset.primary_root.endswith("/")


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_every_dataset_has_at_least_one_filename_timestamp_rule(name):
    assert DATASETS[name].blocks


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_primary_pattern_only_matches_the_primary_file_type(name):
    dataset = DATASETS[name]

    # Usually a bare extension glob ('*.h5'); porotomo_h/porotomo_v are more
    # specific ('PoroTomo_iDAS*_????????????.h5') to exclude a same-extension
    # file that shares their primary_root -- a per-day merged copy of every
    # block, published for HSDS access rather than direct download.
    assert re.search(r"[*?].*\.[A-Za-z0-9]+$", dataset.primary_pattern)
    assert dataset.block_label == dataset.metadata["data"]["format"]


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_access_type_matches_a_provider_cli_py_can_construct(name):
    access = DATASETS[name].metadata["access"]

    assert access["type"] in {
        "globus_https",
        "dataverse_https",
        "zenodo_https",
        "s3_https",
        "pando_https",
        "dropbox_https",
        "huggingface_https",
    }
    assert access["root_path"] == DATASETS[name].dataset_root
    if access["type"] == "globus_https":
        assert "collection_id" in access
    elif access["type"] == "dataverse_https":
        assert "base_url" in access
        assert "persistent_id" in access
    elif access["type"] == "zenodo_https":
        assert "base_url" in access
        assert "record_id" in access
    elif access["type"] == "s3_https":
        assert "base_url" in access
        assert "prefix" in access
    elif access["type"] == "pando_https":
        assert "base_url" in access
        assert "manifest_url" in access
    elif access["type"] == "huggingface_https":
        assert "base_url" in access
        assert "repo_id" in access
        assert "prefix" in access
    else:
        assert "share_url" in access


@pytest.mark.parametrize("name", sorted(DATASETS))
def test_acquisition_configurations_are_selectable(name):
    configs = DATASETS[name].configurations

    assert configs
    if len(configs) == 1:
        return
    # Several configurations are only usable if each says which files used it
    # and at least one selectable setting tells them apart -- otherwise the
    # mandatory --sampling-rate/--channel-spacing/--gauge could never
    # resolve to a subset.
    assert all(not config.is_whole_dataset for config in configs)
    assert any(
        len({getattr(config, field) for config in configs}) > 1
        for field, *_rest in SELECTABLE
    )


def test_config_keys_stay_within_the_documented_schema():
    schema = json.loads((CONFIG_DIR / "schema.json").read_text(encoding="utf-8"))
    allowed = set(schema["properties"])

    for dataset in DATASETS.values():
        assert set(dataset.metadata) <= allowed
        assert set(schema["required"]) <= set(dataset.metadata)


def test_layout_keys_stay_within_the_documented_schema():
    schema = json.loads((CONFIG_DIR / "schema.json").read_text(encoding="utf-8"))
    layout_schema = schema["properties"]["layout"]

    for dataset in DATASETS.values():
        layout = dataset.metadata["layout"]
        assert set(layout) <= set(layout_schema["properties"])
        assert set(layout_schema["required"]) <= set(layout)
