import typing

import pytest
import requests

from daspull.providers.dropbox import DropboxClient, DropboxError

SHARE_URL = (
    "https://www.dropbox.com/scl/fo/fiwbxwfpz65qbx2bu441b/"
    "AKY86kM-Zbbie7_v8v62iKI?rlkey=plqbl8wfb5n90ycpgc7vhms7a"
)
DATASET_ROOT = "/SAFOD/"
FIRST = "2017-06-23T02:54:50.560000Z_mag0.7.npy"
SECOND = "2017-07-01T03:15:13.538000Z_magUNKNOWN.npy"


def file_entry(name, size, *, ts=1567210859):
    return {
        "filename": name,
        "bytes": size,
        "is_dir": False,
        "ts": ts,
        "href": (
            f"https://www.dropbox.com/scl/fo/fiwbxwfpz65qbx2bu441b/"
            f"HASH-{size}/{name}?rlkey=plqbl8wfb5n90ycpgc7vhms7a&dl=0"
        ),
    }


def dir_entry(name):
    return {
        "filename": name,
        "bytes": 0,
        "is_dir": True,
        "ts": None,
        "href": (
            f"https://www.dropbox.com/scl/fo/fiwbxwfpz65qbx2bu441b/"
            f"HASH-{name}/{name}?rlkey=plqbl8wfb5n90ycpgc7vhms7a&dl=0"
        ),
    }


def page(entries, *, voucher=None):
    return {
        "entries": entries,
        "has_more_entries": voucher is not None,
        "next_request_voucher": voucher,
        "total_num_entries": len(entries),
    }


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class FakeCookies(dict):
    pass


class FakeSession:
    """Serves canned listing pages keyed by ``(sub_path, voucher)``."""

    def __init__(self, pages, *, csrf="csrf-token", forbidden_posts=0):
        self.pages = pages
        self.cookies = FakeCookies()
        self.csrf = csrf
        self.forbidden_posts = forbidden_posts
        self.gets = []
        self.posts = []

    def get(self, url, **kwargs):
        self.gets.append(url)
        if self.csrf is not None:
            self.cookies["__Host-js_csrf"] = self.csrf
        return FakeResponse()

    def post(self, url, data=None, **kwargs):
        self.posts.append(data)
        if self.forbidden_posts > 0:
            self.forbidden_posts -= 1
            return FakeResponse(403)
        assert data["t"] == self.csrf
        assert data["link_key"] == "fiwbxwfpz65qbx2bu441b"
        assert data["secure_hash"] == "AKY86kM-Zbbie7_v8v62iKI"
        assert data["rlkey"] == "plqbl8wfb5n90ycpgc7vhms7a"
        key = (data["sub_path"], data.get("voucher"))
        if key not in self.pages:
            return FakeResponse(404)
        return FakeResponse(payload=self.pages[key])


def make_client(pages, **kwargs):
    session = FakeSession(pages, **kwargs)
    return DropboxClient(SHARE_URL, DATASET_ROOT, session=session), session


def flat_pages():
    return {
        ("", None): page([file_entry(FIRST, 100)], voucher="v1"),
        ("", "v1"): page([file_entry(SECOND, 200)]),
    }


def test_iter_files_pages_through_the_whole_folder():
    client, session = make_client(flat_pages())

    files = client.list_files(DATASET_ROOT)

    assert [item.path for item in files] == [
        f"/SAFOD/{FIRST}",
        f"/SAFOD/{SECOND}",
    ]
    assert [item.size for item in files] == [100, 200]
    assert files[0].last_modified == "2019-08-31T00:20:59+00:00"
    # one page-1 request, one voucher request, and no whole-archive download
    assert len(session.posts) == 2
    assert session.gets == [SHARE_URL]


def test_a_listing_is_fetched_once_per_folder():
    client, session = make_client(flat_pages())

    client.list_files(DATASET_ROOT)
    client.list_files(DATASET_ROOT)

    assert len(session.posts) == 2


def test_iter_files_recurses_into_subfolders():
    pages = {
        ("", None): page([dir_entry("nested"), file_entry(FIRST, 100)]),
        ("/nested", None): page([file_entry(SECOND, 200)]),
    }
    client, _ = make_client(pages)

    files = client.list_files(DATASET_ROOT)

    assert [item.path for item in files] == [
        f"/SAFOD/{FIRST}",
        f"/SAFOD/nested/{SECOND}",
    ]


def test_descend_prunes_a_subfolder_before_it_is_listed():
    pages = {
        ("", None): page([dir_entry("nested"), file_entry(FIRST, 100)]),
        ("/nested", None): page([file_entry(SECOND, 200)]),
    }
    client, session = make_client(pages)

    files = list(client.iter_files(DATASET_ROOT, descend=lambda path: False))

    assert [item.path for item in files] == [f"/SAFOD/{FIRST}"]
    assert [data["sub_path"] for data in session.posts] == [""]


def test_stat_file_lists_only_the_parent_folder():
    client, session = make_client(flat_pages())

    remote = client.stat_file(FIRST, root=DATASET_ROOT)

    assert remote.path == f"/SAFOD/{FIRST}"
    assert remote.size == 100
    assert {data["sub_path"] for data in session.posts} == {""}


def test_stat_file_raises_for_an_unknown_path():
    client, _ = make_client(flat_pages())

    with pytest.raises(DropboxError, match="nonexistent.npy"):
        client.stat_file("nonexistent.npy", root=DATASET_ROOT)


def test_download_file_fetches_the_entrys_own_url(monkeypatch, tmp_path):
    calls = []

    def fake_download(url, dest, **kwargs):
        calls.append((url, kwargs))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"a" * kwargs["expected_size"])
        return dest

    monkeypatch.setattr("daspull.providers.dropbox.download", fake_download)
    client, session = make_client(flat_pages())
    remote = client.stat_file(FIRST, root=DATASET_ROOT)

    paths = client.download_files([remote], tmp_path / "out", root=DATASET_ROOT)

    # the ':' in the timestamp is sanitized for the local path, not the URL
    assert paths == [tmp_path / "out" / "2017-06-23T02_54_50.560000Z_mag0.7.npy"]
    url, kwargs = calls[0]
    assert url.startswith(
        f"https://www.dropbox.com/scl/fo/fiwbxwfpz65qbx2bu441b/HASH-100/{FIRST}?"
    )
    assert "dl=1" in url and "dl=0" not in url
    assert kwargs["expected_size"] == 100
    assert kwargs["session"] is session


def test_download_file_rejects_a_file_outside_the_listing(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "daspull.providers.dropbox.download",
        lambda *args, **kwargs: pytest.fail("should not download"),
    )
    client, _ = make_client(flat_pages())
    remote = client.stat_file(FIRST, root=DATASET_ROOT)
    unlisted = type(remote)(path="/SAFOD/ghost.npy", size=10)

    with pytest.raises(DropboxError, match="ghost.npy"):
        client.download_file(unlisted, tmp_path / "ghost.npy")


def test_the_csrf_token_is_fetched_once_and_reused():
    client, session = make_client(flat_pages())

    client.list_files(DATASET_ROOT)
    client.stat_file(SECOND, root=DATASET_ROOT)

    assert session.gets == [SHARE_URL]
    assert {data["t"] for data in session.posts} == {"csrf-token"}


def test_a_rejected_token_is_refreshed_once():
    client, session = make_client(flat_pages(), forbidden_posts=1)

    files = client.list_files(DATASET_ROOT)

    assert len(files) == 2
    assert session.gets == [SHARE_URL, SHARE_URL]


def test_a_persistently_rejected_link_raises():
    client, _ = make_client(flat_pages(), forbidden_posts=5)

    with pytest.raises(DropboxError, match="removed or made private"):
        client.list_files(DATASET_ROOT)


def test_a_share_page_without_a_csrf_cookie_raises():
    client, _ = make_client(flat_pages(), csrf=None)

    with pytest.raises(DropboxError, match="No CSRF cookie"):
        client.list_files(DATASET_ROOT)


def test_an_unknown_folder_raises():
    client, _ = make_client(flat_pages())

    with pytest.raises(DropboxError, match="Not a folder"):
        client.list_files("/SAFOD/missing/")


def test_more_entries_without_a_voucher_raises():
    pages: typing.Any = {("", None): page([file_entry(FIRST, 100)], voucher=None)}
    pages[("", None)]["has_more_entries"] = True
    client, _ = make_client(pages)

    with pytest.raises(DropboxError, match="no pagination voucher"):
        client.list_files(DATASET_ROOT)


def test_a_non_json_listing_response_raises():
    client, _ = make_client({("", None): None})

    with pytest.raises(DropboxError, match="non-JSON"):
        client.list_files(DATASET_ROOT)


def test_an_http_error_from_the_listing_propagates():
    class ErrorSession(FakeSession):
        def post(self, url, data=None, **kwargs):
            self.posts.append(data)
            return FakeResponse(500)

    client = DropboxClient(SHARE_URL, DATASET_ROOT, session=ErrorSession(flat_pages()))

    with pytest.raises(requests.HTTPError):
        client.list_files(DATASET_ROOT)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            SHARE_URL,
            (
                "fiwbxwfpz65qbx2bu441b",
                "AKY86kM-Zbbie7_v8v62iKI",
                "plqbl8wfb5n90ycpgc7vhms7a",
            ),
        ),
        (
            "https://www.dropbox.com/sh/abc123/XYZ789",
            ("abc123", "XYZ789", None),
        ),
    ],
)
def test_both_shared_folder_link_shapes_are_understood(url, expected):
    client = DropboxClient(url, DATASET_ROOT)

    assert (client.link_key, client.secure_hash, client.rlkey) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://www.dropbox.com/scl/fi/abc123/file.npy",
        "https://www.dropbox.com/scl/fo/abc123",
        "https://www.dropbox.com/s/abc123/file.npy",
    ],
)
def test_a_link_that_is_not_a_shared_folder_is_rejected(url):
    with pytest.raises(DropboxError, match="shared-folder link"):
        DropboxClient(url, DATASET_ROOT)
