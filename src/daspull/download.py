from __future__ import annotations

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from urllib.parse import unquote, urlsplit

import requests
from tqdm import tqdm

DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MB
DEFAULT_TIMEOUT = (10, 120)
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_MIN_SPEED = 32 * 1024  # 32 KiB/s floor before a connection counts as stalled
DEFAULT_STALL_TIMEOUT = 45.0  # seconds a connection may stay below min_speed
DEFAULT_PARALLEL_THRESHOLD = 200 * 1024 * 1024  # 200 MB


class DownloadRedirectError(RuntimeError):
    """Raised when a file request redirects to an authentication page."""


class _Stalled(Exception):
    """Raised internally when a stream's throughput drops below the floor for too long."""


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
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    min_speed: float = DEFAULT_MIN_SPEED,
    stall_timeout: float = DEFAULT_STALL_TIMEOUT,
    max_workers: int = 1,
    parallel_threshold: int = DEFAULT_PARALLEL_THRESHOLD,
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
    max_attempts:
        How many times to (re)connect -- via resume -- before giving up,
        including recovery from a stalled connection (see ``min_speed``).
    min_speed:
        Throughput floor in bytes/second. A connection sustained below this
        rate for ``stall_timeout`` seconds is treated as stalled: the
        connection is dropped and resumed from where it left off instead of
        letting a near-frozen transfer run indefinitely.
    stall_timeout:
        How many seconds a connection may stay below ``min_speed`` before
        it is considered stalled.
    max_workers:
        Number of concurrent byte-range connections to use for files at
        least ``parallel_threshold`` bytes. 1 (default) disables parallel
        downloading and preserves the original single-connection behaviour.
    parallel_threshold:
        Minimum ``expected_size`` (bytes) required to use parallel
        byte-range downloading. Small files aren't worth splitting.

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
    client = session or requests

    use_parallel = (
        max_workers > 1
        and expected_size is not None
        and expected_size >= parallel_threshold
        and not tmp_path.exists()
    )

    for attempt in range(max_attempts):
        if use_parallel:
            try:
                _download_parallel(
                    client,
                    url,
                    tmp_path,
                    total=expected_size,
                    workers=max_workers,
                    headers=headers or {},
                    timeout=timeout,
                    min_speed=min_speed,
                    stall_timeout=stall_timeout,
                    desc=dest.name,
                )
            except Exception:
                # Any parallel-segment problem (stall or otherwise) -- don't
                # try to reconcile partial per-segment progress, just fall
                # back to a plain, well-tested sequential resume for the
                # remaining attempts.
                use_parallel = False
                tmp_path.unlink(missing_ok=True)
                if attempt < max_attempts - 1:
                    time.sleep(_backoff(attempt))
                    continue
                raise
        else:
            partial_size = (
                0 if overwrite or not tmp_path.exists() else tmp_path.stat().st_size
            )
            request_headers = dict(headers or {})
            if partial_size:
                request_headers["Range"] = f"bytes={partial_size}-"

            try:
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
                        remote_size = _range_total(
                            response.headers.get("content-range")
                        )
                        if remote_size == partial_size:
                            _validate_partial(
                                tmp_path, checksum, checksum_algo, expected_size
                            )
                            tmp_path.replace(dest)
                            return dest
                        if attempt < max_attempts - 1:
                            tmp_path.unlink(missing_ok=True)
                            continue
                        response.raise_for_status()

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
                    total = (
                        response_size + partial_size
                        if response_size
                        else expected_size or 0
                    )
                    mode = "ab" if resumed else "wb"
                    stall_check = _watch_for_stall(min_speed, stall_timeout)
                    received = partial_size
                    with (
                        open(tmp_path, mode) as f,
                        tqdm(
                            total=total,
                            initial=partial_size,
                            unit="B",
                            unit_scale=True,
                            desc=dest.name,
                            leave=False,
                        ) as bar,
                    ):
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                bar.update(len(chunk))
                                received += len(chunk)
                                stall_check(received)
            except _Stalled:
                if attempt < max_attempts - 1:
                    time.sleep(_backoff(attempt))
                    continue
                raise TimeoutError(
                    f"Download of {dest} stayed below {min_speed:.0f} B/s for over "
                    f"{stall_timeout:.0f}s, even after {max_attempts} attempts"
                )

        if expected_size is not None and tmp_path.stat().st_size != expected_size:
            received_bytes = tmp_path.stat().st_size
            if attempt < max_attempts - 1:
                tmp_path.unlink(missing_ok=True)
                continue
            tmp_path.unlink(missing_ok=True)
            raise OSError(
                f"Size mismatch for {dest}: expected {expected_size} bytes, "
                f"received {received_bytes}"
            )

        _validate_partial(tmp_path, checksum, checksum_algo, expected_size)
        tmp_path.replace(dest)
        return dest

    raise AssertionError("unreachable")  # pragma: no cover


def download_many(urls: list[str], dest_dir: str | Path, **kwargs) -> list[Path]:
    """Download multiple files into a directory, one by one."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    return [download(u, dest_dir, **kwargs) for u in urls]


def _watch_for_stall(min_speed: float, stall_timeout: float):
    """Return a ``check(received_total)`` callback that raises ``_Stalled``
    if throughput over the last ``stall_timeout`` seconds drops below
    ``min_speed`` bytes/second."""
    state = {"time": time.monotonic(), "bytes": 0}

    def check(received_total: int) -> None:
        now = time.monotonic()
        elapsed = now - state["time"]
        if elapsed < stall_timeout:
            return
        rate = (received_total - state["bytes"]) / elapsed
        if rate < min_speed:
            raise _Stalled(f"throughput dropped below {min_speed:.0f} B/s")
        state["time"], state["bytes"] = now, received_total

    return check


def _backoff(attempt: int) -> float:
    return min(2**attempt, 30)


def _split_ranges(total: int, workers: int) -> list[tuple[int, int]]:
    size = -(-total // workers)  # ceil division
    ranges = []
    start = 0
    while start < total:
        end = min(start + size, total)
        ranges.append((start, end))
        start = end
    return ranges


def _download_parallel(
    client,
    url: str,
    tmp_path: Path,
    *,
    total: int,
    workers: int,
    headers: dict[str, str],
    timeout,
    min_speed: float,
    stall_timeout: float,
    desc: str,
) -> None:
    """Fetch ``[0, total)`` as concurrent byte-range requests into one file.

    Each worker opens its own file handle and writes at its own offset, so
    threads never contend for a shared seek position. Any failure (including
    a per-segment stall) raises and lets the caller fall back to a plain
    sequential resume rather than reconciling partial per-segment state.
    """
    with open(tmp_path, "wb") as f:
        f.truncate(total)

    bar_lock = Lock()
    with tqdm(total=total, unit="B", unit_scale=True, desc=desc, leave=False) as bar:

        def fetch(start: int, end: int) -> None:
            range_headers = dict(headers)
            range_headers["Range"] = f"bytes={start}-{end - 1}"
            stall_check = _watch_for_stall(min_speed, stall_timeout)
            received = 0
            with client.get(
                url, stream=True, timeout=timeout, headers=range_headers
            ) as response:
                response.raise_for_status()
                with open(tmp_path, "r+b") as segment_file:
                    segment_file.seek(start)
                    for chunk in response.iter_content(chunk_size=DEFAULT_CHUNK_SIZE):
                        if not chunk:
                            continue
                        segment_file.write(chunk)
                        received += len(chunk)
                        with bar_lock:
                            bar.update(len(chunk))
                        stall_check(received)
            if received != end - start:
                raise OSError(
                    f"Segment bytes={start}-{end - 1} incomplete: received {received} bytes"
                )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(fetch, start, end)
                for start, end in _split_ranges(total, workers)
            ]
            for future in as_completed(futures):
                future.result()


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
