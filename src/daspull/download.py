from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests
from tqdm import tqdm

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MB
DEFAULT_TIMEOUT = (10, 120)


class DownloadRedirectError(RuntimeError):
    """Raised when a file request redirects to an authentication page."""


def download(
    url: str,
    dest: str | Path,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overwrite: bool = False,
    checksum: str | None = None,
    checksum_algo: str = "sha256",
    expected_size: int | None = None,
    headers: dict[str, str] | None = None,
    session: requests.Session | None = None,
    timeout: float | tuple[float, float] = DEFAULT_TIMEOUT,
    allow_redirects: bool = True,
) -> Path:
    """Download a single file via HTTP(S), resuming an existing ``.part`` file.

    Parameters
    ----------
    url:
        Direct URL to the file (e.g. a DAS data repository endpoint).
    dest:
        Local destination path or directory.
    chunk_size:
        Streaming chunk size in bytes.
    overwrite:
        If False (default) and the destination file already exists with
        a matching checksum (when provided) or non-zero size, skip the
        download.
    checksum:
        Optional expected checksum to verify after download.
    checksum_algo:
        Hash algorithm to use for checksum verification.
    expected_size:
        Optional expected file size. Used both to validate the result and to
        distinguish a complete destination from a truncated one.
    headers:
        Optional HTTP request headers, for example an authorization token.
    session:
        Optional requests session to reuse.
    timeout:
        Connect/read timeout passed to requests.
    allow_redirects:
        Whether redirects should be followed. Authenticated data endpoints
        should normally set this to False so a login page is never saved as
        data.

    Returns
    -------
    Path to the downloaded file.
    """
    dest = Path(dest)
    if dest.is_dir():
        filename = Path(unquote(urlsplit(url).path)).name
        if not filename:
            raise ValueError(f"Cannot infer a filename from URL: {url}")
        dest = dest / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not overwrite:
        size_matches = expected_size is None or dest.stat().st_size == expected_size
        if checksum is not None:
            complete = size_matches and _matches_checksum(dest, checksum, checksum_algo)
        elif expected_size is not None:
            complete = size_matches
        else:
            complete = dest.stat().st_size > 0
        if complete:
            return dest
        raise FileExistsError(
            f"{dest} exists but does not match the expected "
            "checksum or size; use overwrite=True to replace it"
        )

    tmp_path = dest.with_suffix(dest.suffix + ".part")
    partial_size = 0 if overwrite or not tmp_path.exists() else tmp_path.stat().st_size
    request_headers = dict(headers or {})
    if partial_size:
        request_headers["Range"] = f"bytes={partial_size}-"

    client = session or requests
    with client.get(
        url,
        stream=True,
        timeout=timeout,
        headers=request_headers,
        allow_redirects=allow_redirects,
    ) as response:
        if not allow_redirects and 300 <= response.status_code < 400:
            location = response.headers.get("location", "<unknown>")
            raise DownloadRedirectError(
                f"Download requires authentication (redirected to {location})"
            )

        if response.status_code == 416 and partial_size:
            remote_size = _range_total(response.headers.get("content-range"))
            if remote_size == partial_size:
                _validate_partial(tmp_path, checksum, checksum_algo, expected_size)
                tmp_path.replace(dest)
                return dest

        response.raise_for_status()

        resumed = partial_size > 0 and response.status_code == 206
        if resumed:
            content_range = response.headers.get("content-range", "")
            if not content_range.startswith(f"bytes {partial_size}-"):
                raise OSError(
                    f"Server returned an unexpected Content-Range: {content_range!r}"
                )
        else:
            partial_size = 0

        response_size = int(response.headers.get("content-length", 0))
        total = response_size + partial_size if response_size else expected_size or 0
        mode = "ab" if resumed else "wb"
        with (
            open(tmp_path, mode) as f,
            tqdm(
                total=total,
                initial=partial_size,
                unit="B",
                unit_scale=True,
                desc=dest.name,
            ) as bar,
        ):
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))

    if expected_size is not None and tmp_path.stat().st_size != expected_size:
        raise OSError(
            f"Size mismatch for {dest}: expected {expected_size} bytes, "
            f"received {tmp_path.stat().st_size}"
        )

    _validate_partial(tmp_path, checksum, checksum_algo, expected_size)
    tmp_path.replace(dest)
    return dest


def download_many(urls: list[str], dest_dir: str | Path, **kwargs) -> list[Path]:
    """Download multiple files into a directory, one by one."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    return [download(u, dest_dir, **kwargs) for u in urls]


def _matches_checksum(path: Path, expected: str, algo: str) -> bool:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest() == expected.lower()


def _validate_download(
    path: Path,
    checksum: str | None,
    checksum_algo: str,
    expected_size: int | None,
) -> Path:
    if expected_size is not None and path.stat().st_size != expected_size:
        raise OSError(
            f"Size mismatch for {path}: expected {expected_size} bytes, "
            f"received {path.stat().st_size}"
        )
    if checksum is not None and not _matches_checksum(path, checksum, checksum_algo):
        raise ValueError(f"Checksum mismatch for {path}")
    return path


def _validate_partial(
    path: Path,
    checksum: str | None,
    checksum_algo: str,
    expected_size: int | None,
) -> None:
    try:
        _validate_download(path, checksum, checksum_algo, expected_size)
    except ValueError:
        # A full-size file with the wrong digest cannot be resumed safely.
        path.unlink(missing_ok=True)
        raise


def _range_total(content_range: str | None) -> int | None:
    if not content_range or "/" not in content_range:
        return None
    value = content_range.rsplit("/", 1)[-1]
    return int(value) if value.isdigit() else None
