"""The package's public surface: what ``import daspull`` promises to expose."""

import daspull


def test_version():
    assert daspull.__version__ == "0.1.0"


def test_every_exported_name_resolves():
    # __all__ is written by hand while the names it lists are re-exported from
    # the subpackages (daspull.api, daspull.datasets, daspull.providers.*), so a
    # module move that forgets one fails here instead of in a caller's import.
    assert [name for name in daspull.__all__ if not hasattr(daspull, name)] == []


def test_the_package_level_download_is_the_dataset_facade():
    assert daspull.download is daspull.api.download
    # That facade shadows the same-named *module* attribute, so the low-level
    # fetcher is reachable as `daspull.download_url`, or as `from
    # daspull.download import download` -- never as `daspull.download.download`.
    assert not hasattr(daspull.download, "download")
    assert callable(daspull.download_url)
