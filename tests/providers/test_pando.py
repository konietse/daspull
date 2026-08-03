import requests

from daspull.providers.pando import PandoClient, PandoError

BASE_URL = "https://pando-rgw01.chpc.utah.edu"
MANIFEST_URL = "https://constantine.seis.utah.edu/files/get_all_silixa.sh"
DATASET_ROOT = "/FORGE_2C/"

MANIFEST_TEXT = """#!/bin/bash
wget -q https://pando-rgw01.chpc.utah.edu/silixa_das_apr_19_2019/FORGE_78-32_iDASv3-P11_UTC190419001218.sgy
wget -q https://pando-rgw01.chpc.utah.edu/silixa_das_apr_19_2019/FORGE_78-32_iDASv3-P11_UTC190419001233.sgy
wget -q https://pando-rgw01.chpc.utah.edu/silixa_das_may_03_2019/FORGE_78-32_iDASv3-P11_UTC190503131438.sgy
"""


class TextResponse:
    def __init__(self, text, *, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class FakeResponse:
    def __init__(self, *, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class ManifestSession:
    def __init__(self):
        self.get_calls = []
        self.head_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        assert url == MANIFEST_URL
        return TextResponse(MANIFEST_TEXT)

    def head(self, url, **kwargs):
        self.head_calls.append((url, kwargs))
        if url == (
            f"{BASE_URL}/silixa_das_apr_19_2019/"
            "FORGE_78-32_iDASv3-P11_UTC190419001218.sgy"
        ):
            return FakeResponse(
                headers={
                    "Content-Length": "130824720",
                    "ETag": '"2873809e769c3045cd7648181bb27743"',
                    "Last-Modified": "Wed, 05 Feb 2020 21:26:23 GMT",
                }
            )
        return FakeResponse(status_code=404)


def make_client(session=None):
    return PandoClient(
        BASE_URL, MANIFEST_URL, DATASET_ROOT, session=session or ManifestSession()
    )


def test_iter_files_synthesizes_paths_directly_below_root():
    client = make_client()

    files = client.list_files(DATASET_ROOT)

    assert [item.path for item in files] == [
        "/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190419001218.sgy",
        "/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190419001233.sgy",
        "/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190503131438.sgy",
    ]


def test_iter_files_never_issues_a_head_request():
    session = ManifestSession()
    client = make_client(session)

    files = list(client.iter_files(DATASET_ROOT))

    assert all(item.size == 0 for item in files)
    assert all(item.checksum is None for item in files)
    assert not session.head_calls


def test_descend_is_accepted_but_has_no_effect():
    client = make_client()

    files = list(client.iter_files(DATASET_ROOT, descend=lambda path: False))

    assert len(files) == 3


def test_manifest_is_fetched_only_once_across_calls():
    session = ManifestSession()
    client = make_client(session)

    client.list_files(DATASET_ROOT)
    client.stat_file("FORGE_78-32_iDASv3-P11_UTC190419001218.sgy", root=DATASET_ROOT)
    list(client.iter_files(DATASET_ROOT))

    assert len(session.get_calls) == 1


def test_stat_file_resolves_a_root_relative_literal_path_via_head():
    client = make_client()

    remote = client.stat_file(
        "FORGE_78-32_iDASv3-P11_UTC190419001218.sgy", root=DATASET_ROOT
    )

    assert remote.path == "/FORGE_2C/FORGE_78-32_iDASv3-P11_UTC190419001218.sgy"
    assert remote.size == 130824720
    assert remote.checksum == "2873809e769c3045cd7648181bb27743"


def test_stat_file_raises_for_a_path_outside_the_manifest():
    client = make_client()

    try:
        client.stat_file("nonexistent.sgy", root=DATASET_ROOT)
    except PandoError as exc:
        assert "nonexistent.sgy" in str(exc)
    else:
        raise AssertionError("Expected PandoError")


def test_download_file_heads_an_unresolved_placeholder_before_downloading(
    monkeypatch, tmp_path
):
    captured = {}

    def fake_download(url, dest, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return dest

    monkeypatch.setattr("daspull.providers.pando.download", fake_download)
    session = ManifestSession()
    client = make_client(session)
    remote = next(
        item
        for item in client.iter_files(DATASET_ROOT)
        if item.name == "FORGE_78-32_iDASv3-P11_UTC190419001218.sgy"
    )
    assert remote.size == 0

    client.download_files([remote], tmp_path, root=DATASET_ROOT)

    assert len(session.head_calls) == 1
    assert captured["url"] == (
        f"{BASE_URL}/silixa_das_apr_19_2019/FORGE_78-32_iDASv3-P11_UTC190419001218.sgy"
    )
    assert captured["kwargs"]["expected_size"] == 130824720
    assert captured["kwargs"]["checksum"] == "2873809e769c3045cd7648181bb27743"
    assert captured["kwargs"]["checksum_algo"] == "md5"


def test_download_file_trusts_a_size_already_resolved_by_stat_file(
    monkeypatch, tmp_path
):
    def fake_download(url, dest, **kwargs):
        return dest

    monkeypatch.setattr("daspull.providers.pando.download", fake_download)
    session = ManifestSession()
    client = make_client(session)
    remote = client.stat_file(
        "FORGE_78-32_iDASv3-P11_UTC190419001218.sgy", root=DATASET_ROOT
    )
    assert len(session.head_calls) == 1

    client.download_files([remote], tmp_path, root=DATASET_ROOT)

    assert len(session.head_calls) == 1


def test_multipart_style_etag_is_not_used_as_a_checksum(monkeypatch):
    class DashedEtagSession(ManifestSession):
        def head(self, url, **kwargs):
            self.head_calls.append((url, kwargs))
            return FakeResponse(
                headers={
                    "Content-Length": "130824720",
                    "ETag": '"abcdef0123456789abcdef0123456789-2"',
                }
            )

    client = make_client(DashedEtagSession())

    remote = client.stat_file(
        "FORGE_78-32_iDASv3-P11_UTC190419001218.sgy", root=DATASET_ROOT
    )

    assert remote.checksum is None
