"""Shared test helpers: UTC timestamps and a stand-in dataset client.

:class:`FakeClient` is the single fake ``DatasetClient`` both front-end test
modules drive. Keeping one implementation here means a change to the client
contract in ``daspull/client.py`` breaks one fake rather than two copies that
had drifted apart.
"""

from __future__ import annotations

from datetime import datetime, timezone

from daspull.catalog import RemoteFile


def utc(value: str) -> datetime:
    """Parse ``YYYY-MM-DD HH:MM:SS`` or ``YYYY-MM-DD HH:MM:SS.mmm`` as UTC."""
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in value else "%Y-%m-%d %H:%M:%S"
    return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)


class FakeClient:
    """A ``DatasetClient`` over a fixed file list, recording what it was asked.

    Entries may be ``RemoteFile`` objects or bare paths, which become 100-byte
    files -- most tests care about which names came back, not their sizes.
    """

    def __init__(self, files=()):
        self.files = [
            item if isinstance(item, RemoteFile) else RemoteFile(item, 100)
            for item in files
        ]
        self.roots: list[str] = []
        self.descend = None
        self.downloaded: list[RemoteFile] = []
        self.destinations: list[str] = []

    def iter_files(self, root, *, descend=None):
        self.roots.append(root)
        self.descend = descend
        yield from self.files

    def stat_file(self, path, *, root):
        for remote in self.files:
            if remote.path == path:
                return remote
        raise FileNotFoundError(path)

    def download_files(self, files, dest_dir, *, root, overwrite=False):
        self.downloaded.extend(files)
        self.destinations.append(str(dest_dir))
        return [dest_dir]


class FakeTokenStore:
    """A ``TokenStore`` that hands out tokens without touching disk or Globus."""

    def access_token(self):
        return "transfer-token"

    def access_token_for_scope(self, scope):
        return "https-token"


def install_fake_globus_client(monkeypatch, files=()):
    """Point every Globus dataset at one :class:`FakeClient`, and return it.

    Patches the two names ``providers.build_client`` looks up in its own module
    globals -- which is exactly why they are imported at module level in
    ``daspull/providers/__init__.py`` rather than inside the function.
    """
    client = FakeClient(files)
    monkeypatch.setattr("daspull.providers.TokenStore", FakeTokenStore)
    monkeypatch.setattr(
        "daspull.providers.PubDASClient", lambda *args, **kwargs: client
    )
    return client
