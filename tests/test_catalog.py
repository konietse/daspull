from pathlib import Path

import pytest

from daspull.catalog import clean_remote_path, local_relative_path, relative_to_root


def test_local_relative_path_matches_relative_to_root_when_already_safe():
    path = "/PoroTomo_H/20160311/PoroTomo_iDAS16043_160311164618.h5"
    root = "/PoroTomo_H/"

    assert local_relative_path(path, root) == relative_to_root(path, root)


def test_local_relative_path_replaces_windows_illegal_characters():
    path = "/SAFOD/2017-06-23T02:54:50.560000Z_mag0.7.npy"
    root = "/SAFOD/"

    assert local_relative_path(path, root) == Path(
        "2017-06-23T02_54_50.560000Z_mag0.7.npy"
    )


def test_local_relative_path_leaves_relative_to_root_itself_exact():
    # Matching/selection must still see the real remote path with its colons.
    path = "/SAFOD/2017-06-23T02:54:50.560000Z_mag0.7.npy"
    root = "/SAFOD/"

    assert relative_to_root(path, root) == Path(
        "2017-06-23T02:54:50.560000Z_mag0.7.npy"
    )


def test_clean_remote_path_rejects_backslash():
    # A remote filename carrying a backslash could re-split into ``..``
    # traversal components once handed to a native (Windows) Path.
    with pytest.raises(ValueError, match="Unsafe remote path"):
        clean_remote_path("/Fairbanks/..\\..\\..\\Temp\\evil.txt")


def test_clean_remote_path_rejects_drive_letter_component():
    # A component like "D:secret.txt" resets a native Path join onto a
    # different drive entirely, discarding the intended destination directory.
    with pytest.raises(ValueError, match="Unsafe remote path"):
        clean_remote_path("/Fairbanks/foo/D:secret.txt")
