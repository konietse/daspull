import sys
import time
from pathlib import Path
from threading import Lock

import pytest

from daspull.download import DownloadRedirectError, download, download_many

download_module = sys.modules["daspull.download"]


class FakeResponse:
    def __init__(self, body=b"", *, status_code=200, headers=None):
        self.body = body
        self.status_code = status_code
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        yield self.body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class SequenceSession:
    """Returns one canned response per call, in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses[len(self.calls) - 1]


def test_download_resumes_part_file(tmp_path):
    destination = tmp_path / "sample.tdms"
    part = tmp_path / "sample.tdms.part"
    part.write_bytes(b"abc")
    session = FakeSession(
        FakeResponse(
            b"def",
            status_code=206,
            headers={"content-length": "3", "content-range": "bytes 3-5/6"},
        )
    )

    result = download(
        "https://data.example/sample.tdms",
        destination,
        expected_size=6,
        session=session,
    )

    assert result == destination
    assert destination.read_bytes() == b"abcdef"
    assert session.calls[0][1]["headers"]["Range"] == "bytes=3-"


def test_download_discards_stale_part_after_mismatched_416(tmp_path):
    """A .part left over from before the remote file changed size can't be resumed."""
    destination = tmp_path / "sample.tdms"
    part = tmp_path / "sample.tdms.part"
    part.write_bytes(b"stale-and-too-long")

    session = SequenceSession(
        [
            FakeResponse(status_code=416, headers={"content-range": "bytes */6"}),
            FakeResponse(b"abcdef", status_code=200, headers={"content-length": "6"}),
        ]
    )

    result = download(
        "https://data.example/sample.tdms",
        destination,
        expected_size=6,
        session=session,
    )

    assert result == destination
    assert destination.read_bytes() == b"abcdef"
    assert len(session.calls) == 2
    assert "Range" not in session.calls[1][1]["headers"]


def test_download_retries_once_after_size_mismatch(tmp_path):
    """A completed download that doesn't match expected_size should be discarded and retried once."""
    destination = tmp_path / "sample.tdms"
    part = tmp_path / "sample.tdms.part"

    session = SequenceSession(
        [
            FakeResponse(b"short", status_code=200, headers={"content-length": "5"}),
            FakeResponse(b"abcdef", status_code=200, headers={"content-length": "6"}),
        ]
    )

    result = download(
        "https://data.example/sample.tdms",
        destination,
        expected_size=6,
        session=session,
    )

    assert result == destination
    assert destination.read_bytes() == b"abcdef"
    assert not part.exists()
    assert len(session.calls) == 2


def test_download_rejects_redirect_when_disabled(tmp_path):
    session = FakeSession(
        FakeResponse(status_code=302, headers={"location": "https://login.example/"})
    )

    with pytest.raises(DownloadRedirectError, match="authentication"):
        download(
            "https://data.example/sample.tdms",
            tmp_path / "sample.tdms",
            session=session,
            allow_redirects=False,
        )


def test_existing_file_must_have_expected_size(tmp_path):
    destination = tmp_path / "sample.tdms"
    destination.write_bytes(b"short")

    with pytest.raises(FileExistsError, match="does not match"):
        download(
            "https://data.example/sample.tdms",
            destination,
            expected_size=100,
        )


def test_checksum_takes_precedence_over_matching_size(tmp_path):
    destination = tmp_path / "sample.tdms"
    destination.write_bytes(b"wrong")

    with pytest.raises(FileExistsError, match="does not match"):
        download(
            "https://data.example/sample.tdms",
            destination,
            expected_size=5,
            checksum="0" * 64,
        )


def test_destination_directory_uses_url_path_name(tmp_path):
    session = FakeSession(FakeResponse(b"data", headers={"content-length": "4"}))

    result = download(
        "https://data.example/files/sample.tdms?download=1",
        Path(tmp_path),
        expected_size=4,
        session=session,
    )

    assert result.name == "sample.tdms"
    assert result.read_bytes() == b"data"


def test_download_recovers_from_a_stalled_connection(tmp_path, monkeypatch):
    """A connection stuck far below the speed floor is dropped and resumed
    rather than being allowed to trickle along indefinitely."""
    monkeypatch.setattr(download_module, "_backoff", lambda attempt: 0)
    destination = tmp_path / "sample.tdms"

    class StallingResponse(FakeResponse):
        def iter_content(self, chunk_size):
            yield b"a"
            time.sleep(0.08)
            yield b"b"

    session = SequenceSession(
        [
            StallingResponse(status_code=200, headers={"content-length": "6"}),
            FakeResponse(
                b"cdef",
                status_code=206,
                headers={"content-length": "4", "content-range": "bytes 2-5/6"},
            ),
        ]
    )

    result = download(
        "https://data.example/sample.tdms",
        destination,
        expected_size=6,
        session=session,
        stall_timeout=0.05,
        min_speed=1_000_000,
    )

    assert result == destination
    assert destination.read_bytes() == b"abcdef"
    assert len(session.calls) == 2
    # The stalled connection is dropped and resumed from where it left off,
    # not restarted from scratch.
    assert session.calls[1][1]["headers"]["Range"] == "bytes=2-"


class RangeSession:
    """Serves byte ranges of a fixed payload, regardless of which worker asks."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self._lock = Lock()

    def get(self, url, **kwargs):
        with self._lock:
            self.calls.append((url, kwargs))
        start, end = kwargs["headers"]["Range"].removeprefix("bytes=").split("-")
        start, end = int(start), int(end)
        body = self.payload[start : end + 1]
        return FakeResponse(
            body, status_code=206, headers={"content-length": str(len(body))}
        )


def test_download_uses_parallel_ranges_for_large_files(tmp_path):
    payload = bytes(range(256)) * 100  # 25,600 bytes
    destination = tmp_path / "big.h5"
    session = RangeSession(payload)

    result = download(
        "https://data.example/big.h5",
        destination,
        expected_size=len(payload),
        session=session,
        max_workers=4,
        parallel_threshold=1,
    )

    assert result == destination
    assert destination.read_bytes() == payload
    assert len(session.calls) == 4


def test_download_many_creates_destination_directory(tmp_path):
    destination = tmp_path / "new-directory"
    session = FakeSession(FakeResponse(b"data", headers={"content-length": "4"}))

    paths = download_many(
        ["https://data.example/sample.tdms"],
        destination,
        expected_size=4,
        session=session,
    )

    assert paths == [destination / "sample.tdms"]
    assert paths[0].read_bytes() == b"data"
