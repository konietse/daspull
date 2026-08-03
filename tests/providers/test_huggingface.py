import pytest
import requests

from daspull.providers.huggingface import HuggingFaceClient, HuggingFaceError

BASE_URL = "https://huggingface.co"
REPO_ID = "AI4EPS/quakeflow_das"
PREFIX = "eureka/data/"
DATASET_ROOT = "/GorDAS-1/"

TREE = f"{BASE_URL}/api/datasets/{REPO_ID}/tree/main"
RESOLVE = f"{BASE_URL}/datasets/{REPO_ID}/resolve/main"

EVENT = "2022-06-03T20:46:03.530Z"
EVENT_QUOTED = "2022-06-03T20%3A46%3A03.530Z"
FIRST = "Eureka-DT1087-2m-P5kHz-fs250Hz_2022-06-03T204121Z.h5"
SECOND = "Eureka-DT1087-2m-P5kHz-fs250Hz_2022-06-03T204221Z.h5"
SHA = "e09d8d1b5bc7b76a7fbd8f1322e629df9befb32302fd5f3fc11c6cdb50e85ff3"


def lfs_file(path, size, oid):
    return {
        "type": "file",
        "oid": "0511a7c589c8aaddeeb3dd71f813990d5a0b240f",
        "size": size,
        "lfs": {"oid": oid, "size": size, "pointerSize": 134},
        "path": path,
    }


def plain_file(path, size):
    return {
        "type": "file",
        "oid": "f4f3945bd7150d3e12988485c42da1f8c29c59f8",
        "size": size,
        "path": path,
    }


def directory(path):
    return {"type": "directory", "oid": "690c40cda2d99559", "size": 0, "path": path}


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class RepoSession:
    """Serves canned tree pages and resolve redirects for one repo."""

    def __init__(self):
        self.gets = []
        self.heads = []
        self.page_two_served = False

    def get(self, url, **kwargs):
        self.gets.append(url)
        if url == f"{TREE}/eureka/data":
            return FakeResponse([directory(f"{PREFIX}{EVENT}")])
        if url == f"{TREE}/eureka/data/{EVENT_QUOTED}":
            return FakeResponse(
                [lfs_file(f"{PREFIX}{EVENT}/{FIRST}", 169607757, SHA)],
                headers={
                    "link": f'<{TREE}/eureka/data/{EVENT_QUOTED}?cursor=x>; rel="next"'
                },
            )
        if url == f"{TREE}/eureka/data/{EVENT_QUOTED}?cursor=x":
            self.page_two_served = True
            return FakeResponse(
                [
                    lfs_file(f"{PREFIX}{EVENT}/{SECOND}", 170117065, "b" * 64),
                    plain_file(f"{PREFIX}{EVENT}/notes.txt", 12),
                ]
            )
        return FakeResponse(
            status_code=404, headers={"x-error-message": "does not exist"}
        )

    def head(self, url, **kwargs):
        self.heads.append((url, kwargs))
        if url == f"{RESOLVE}/eureka/data/{EVENT_QUOTED}/{FIRST}":
            return FakeResponse(
                status_code=302,
                headers={
                    "x-linked-size": "169607757",
                    "x-linked-etag": f'"{SHA}"',
                    "last-modified": "Wed, 05 Sep 2024 18:05:13 GMT",
                },
            )
        return FakeResponse(status_code=404)


def make_client(session=None, **kwargs):
    return HuggingFaceClient(
        BASE_URL,
        REPO_ID,
        PREFIX,
        DATASET_ROOT,
        session=session or RepoSession(),
        **kwargs,
    )


def test_iter_files_walks_the_repo_tree_below_the_prefix():
    client = make_client()

    files = client.list_files(DATASET_ROOT)

    assert [item.path for item in files] == [
        f"/GorDAS-1/{EVENT}/{FIRST}",
        f"/GorDAS-1/{EVENT}/{SECOND}",
        f"/GorDAS-1/{EVENT}/notes.txt",
    ]
    assert files[0].size == 169607757


def test_pagination_follows_the_link_header():
    session = RepoSession()
    client = make_client(session)

    list(client.iter_files(DATASET_ROOT))

    assert session.page_two_served


def test_descend_genuinely_prunes_a_subtree():
    session = RepoSession()
    client = make_client(session)

    files = list(client.iter_files(DATASET_ROOT, descend=lambda path: False))

    assert files == []
    assert session.gets == [f"{TREE}/eureka/data"]


def test_an_lfs_oid_is_used_as_a_sha256_checksum():
    client = make_client()

    files = client.list_files(DATASET_ROOT)

    assert files[0].checksum == SHA


def test_a_plain_git_blob_sha1_is_not_used_as_a_checksum():
    client = make_client()

    files = client.list_files(DATASET_ROOT)

    assert files[2].name == "notes.txt"
    assert files[2].checksum is None


def test_stat_file_reads_the_download_redirect_without_following_it():
    session = RepoSession()
    client = make_client(session)

    remote = client.stat_file(f"{EVENT}/{FIRST}", root=DATASET_ROOT)

    assert remote.path == f"/GorDAS-1/{EVENT}/{FIRST}"
    assert remote.size == 169607757
    assert remote.checksum == SHA
    assert session.heads[0][1]["allow_redirects"] is False
    assert session.gets == []


def test_stat_file_raises_for_a_missing_file():
    client = make_client()

    with pytest.raises(HuggingFaceError, match="nonexistent.h5"):
        client.stat_file(f"{EVENT}/nonexistent.h5", root=DATASET_ROOT)


def test_listing_a_missing_directory_raises():
    client = make_client()

    with pytest.raises(HuggingFaceError, match="Not a directory"):
        client.list_files(f"{DATASET_ROOT}missing/")


def test_a_path_outside_the_dataset_root_is_rejected():
    client = make_client()

    with pytest.raises(HuggingFaceError, match="outside dataset root"):
        list(client.iter_files("/SomewhereElse/"))


def test_download_files_maps_the_virtual_path_to_the_repo_path(monkeypatch, tmp_path):
    captured = {}

    def fake_download(url, dest, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return dest

    monkeypatch.setattr("daspull.providers.huggingface.download", fake_download)
    session = RepoSession()
    client = make_client(session)
    remote = client.stat_file(f"{EVENT}/{FIRST}", root=DATASET_ROOT)

    paths = client.download_files([remote], tmp_path, root=DATASET_ROOT)

    # the ':' in the event directory is sanitized for the local path but
    # percent-encoded, not dropped, in the URL
    assert paths == [tmp_path / "2022-06-03T20_46_03.530Z" / FIRST]
    assert captured["url"] == f"{RESOLVE}/eureka/data/{EVENT_QUOTED}/{FIRST}"
    assert captured["kwargs"]["expected_size"] == 169607757
    assert captured["kwargs"]["checksum"] == SHA
    # the SHA-256 default is what an LFS oid needs; no algo override is passed
    assert "checksum_algo" not in captured["kwargs"]
    assert captured["kwargs"]["session"] is session


def test_a_pinned_revision_is_used_for_both_listing_and_downloads():
    session = RepoSession()
    client = make_client(session, revision="abc123")

    with pytest.raises(HuggingFaceError):
        client.list_files(DATASET_ROOT)
    assert session.gets == [
        f"{BASE_URL}/api/datasets/{REPO_ID}/tree/abc123/eureka/data"
    ]
    assert client._file_url("eureka/data/x.h5") == (
        f"{BASE_URL}/datasets/{REPO_ID}/resolve/abc123/eureka/data/x.h5"
    )
