"""Dependency-light access to a dataset hosted on CHPC's Pando object store."""

from __future__ import annotations

import atexit
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path

import certifi
import requests

from ..catalog import (
    RemoteFile,
    directory_path,
    local_relative_path,
    resolve_literal_path,
)
from ..download import download

DEFAULT_TIMEOUT = (10, 120)
_MANIFEST_LINE = re.compile(r"^wget\s+-q\s+(\S+)", re.MULTILINE)

# InCommon RSA Server CA 2, issued by USERTrust RSA Certification Authority
# (a root already in certifi), valid until 2032-11-15. This is the specific
# intermediate constantine.seis.utah.edu omits from its own TLS handshake;
# see the module docstring. Fetched from the certificate's own AIA "CA
# Issuers" URL (http://crt.sectigo.com/InCommonRSAServerCA2.crt).
_INCOMMON_RSA_SERVER_CA_2_PEM = """\
-----BEGIN CERTIFICATE-----
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
-----END CERTIFICATE-----
"""

_ca_bundle_path: str | None = None


def _manifest_ca_bundle() -> str:
    """Return a CA bundle path completing constantine.seis.utah.edu's chain.

    Built once per process from certifi's own root bundle plus the one
    intermediate certificate that host fails to send, so verification stays
    exactly as strict as `requests`' default -- this only *adds* a
    legitimately-issued path to a trusted root, it removes nothing.
    """
    global _ca_bundle_path
    if _ca_bundle_path is None:
        certifi_bundle = Path(certifi.where()).read_bytes()
        fd, path = tempfile.mkstemp(prefix="daspull-ca-", suffix=".pem")
        with os.fdopen(fd, "wb") as handle:
            handle.write(certifi_bundle)
            handle.write(b"\n")
            handle.write(_INCOMMON_RSA_SERVER_CA_2_PEM.encode("ascii"))
        atexit.register(os.remove, path)
        _ca_bundle_path = path
    return _ca_bundle_path


class PandoError(RuntimeError):
    """Raised when a Pando-hosted file cannot be resolved or downloaded."""


class PandoClient:
    """Browse and download a dataset published via a static Pando manifest."""

    def __init__(
        self,
        base_url: str,
        manifest_url: str,
        dataset_root: str,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.manifest_url = manifest_url
        self.dataset_root = dataset_root
        if session is None:
            session = requests.Session()
            # Only for a session we create ourselves -- a caller-supplied
            # session keeps whatever TLS trust configuration it already has.
            session.verify = _manifest_ca_bundle()
        self.session = session
        self._entries: dict[str, tuple[RemoteFile, str]] | None = None

    def list_files(self, root: str) -> list[RemoteFile]:
        """List every catalogued file below *root*."""
        return sorted(self.iter_files(root), key=lambda item: item.path)

    def iter_files(
        self,
        root: str,
        *,
        descend: Callable[[str], bool] | None = None,
    ) -> Iterator[RemoteFile]:
        """Yield every catalogued file below *root*.

        The manifest is fetched and parsed whole, so there is no subtree for
        *descend* to prune; it is accepted only so this method interchanges
        with the other providers' clients. Entries come straight from the
        manifest -- size ``0`` and no checksum -- since getting real metadata
        would mean one `HEAD` request per catalogued file.
        """
        del descend
        root = directory_path(root)
        for remote, _ in self._catalog().values():
            if remote.path.startswith(root):
                yield remote

    def stat_file(self, path: str, *, root: str) -> RemoteFile:
        """Resolve one exact dataset path and fill in its real metadata.

        Unlike :meth:`iter_files`, this is a single file, so the one extra
        `HEAD` request needed to get an accurate size and checksum is cheap.
        """
        remote_path = resolve_literal_path(path, root)
        entry = self._catalog().get(remote_path)
        if entry is None:
            raise PandoError(f"Not a file in this manifest: {remote_path}")
        _, url = entry
        return self._head(remote_path, url)

    def download_file(
        self,
        remote: RemoteFile,
        dest: str | Path,
        *,
        overwrite: bool = False,
    ) -> Path:
        """Download one catalogued file, preserving resumable partial data."""
        entry = self._catalog().get(remote.path)
        if entry is None:
            raise PandoError(f"Not a file in this manifest: {remote.path}")
        _, url = entry
        # A placeholder from iter_files (size 0, no checksum) is refreshed
        # with a HEAD before the transfer; one already resolved via
        # stat_file is trusted as-is rather than re-fetched.
        resolved = remote if remote.size else self._head(remote.path, url)
        return download(
            url,
            dest,
            overwrite=overwrite,
            expected_size=resolved.size or None,
            checksum=resolved.checksum,
            checksum_algo="md5",
            session=self.session,
        )

    def download_files(
        self,
        files: list[RemoteFile],
        dest_dir: str | Path,
        *,
        root: str,
        overwrite: bool = False,
    ) -> list[Path]:
        """Download files while preserving their paths relative to *root*."""
        root = directory_path(root)
        destination = Path(dest_dir)
        results: list[Path] = []
        for remote in files:
            relative = local_relative_path(remote.path, root)
            results.append(
                self.download_file(remote, destination / relative, overwrite=overwrite)
            )
        return results

    def _catalog(self) -> dict[str, tuple[RemoteFile, str]]:
        """Fetch and cache the manifest, keyed by virtual path."""
        if self._entries is None:
            response = self.session.get(self.manifest_url, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            self._entries = dict(self._parse_manifest(response.text))
        return self._entries

    def _parse_manifest(
        self, text: str
    ) -> Iterator[tuple[str, tuple[RemoteFile, str]]]:
        root = directory_path(self.dataset_root)
        for url in _MANIFEST_LINE.findall(text):
            if not url.startswith(f"{self.base_url}/"):
                continue
            filename = url.rsplit("/", 1)[-1]
            path = f"{root}{filename}"
            yield path, (RemoteFile(path=path, size=0), url)

    def _head(self, remote_path: str, url: str) -> RemoteFile:
        response = self.session.head(url, timeout=DEFAULT_TIMEOUT)
        if response.status_code == 404:
            raise PandoError(f"Not a file on Pando: {remote_path}")
        response.raise_for_status()
        return RemoteFile(
            path=remote_path,
            size=int(response.headers.get("Content-Length") or 0),
            last_modified=response.headers.get("Last-Modified"),
            checksum=_checksum_from_etag(response.headers.get("ETag")),
        )


def _checksum_from_etag(etag: str | None) -> str | None:
    """Return a plain (non-multipart) ETag as an MD5 digest, else ``None``."""
    if not etag:
        return None
    value = etag.strip('"')
    if "-" in value:
        return None
    return value
