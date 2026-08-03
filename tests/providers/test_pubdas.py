import requests

from daspull.catalog import RemoteFile, select_files
from daspull.providers.pubdas import PubDASAuthenticationError, PubDASClient

FAIRBANKS_ROOT = "/Fairbanks/"


class JsonResponse:
    def __init__(self, payload, *, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class CatalogSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        path = (kwargs.get("params") or {}).get("path")
        if url.endswith("/endpoint/706e304c-5def-11ec-9b5c-f9dfb1abb183"):
            return JsonResponse({"https_server": "https://data.example/"})
        if url.endswith("/stat") and path == "/Fairbanks/citation.txt":
            return JsonResponse(
                {
                    "name": "citation.txt",
                    "type": "file",
                    "size": 734,
                    "last_modified": "2023-01-01 00:00:00+00:00",
                }
            )
        if path == "/Fairbanks/":
            return JsonResponse(
                {
                    "DATA": [
                        {"name": "README.txt", "type": "file", "size": 12},
                        {"name": "2017", "type": "dir", "size": 0},
                        {"name": "../escape", "type": "file", "size": 10},
                    ]
                }
            )
        if path == "/Fairbanks/2017/":
            return JsonResponse(
                {
                    "DATA": [
                        {
                            "name": "shot-01.tdms",
                            "type": "file",
                            "size": 100,
                            "last_modified": "2017-08-01 00:00:00+00:00",
                        }
                    ]
                }
            )
        raise AssertionError(f"Unexpected request: {url} {kwargs}")


def test_recursively_lists_fairbanks_catalog():
    client = PubDASClient("transfer-token", session=CatalogSession())

    files = client.list_files(FAIRBANKS_ROOT)

    assert [item.path for item in files] == [
        "/Fairbanks/2017/shot-01.tdms",
        "/Fairbanks/README.txt",
    ]
    assert files[0].size == 100
    assert client.collection_https_url() == "https://data.example"


def test_select_files_matches_basenames_and_relative_paths():
    files = [
        RemoteFile("/Fairbanks/2017/a.tdms", 10),
        RemoteFile("/Fairbanks/2017/b.tdms", 20),
        RemoteFile("/Fairbanks/README.txt", 5),
    ]

    selected = select_files(
        files,
        root=FAIRBANKS_ROOT,
        include=["*.tdms"],
        exclude=["2017/b*"],
    )

    assert selected == [files[0]]


def test_select_files_matches_absolute_dataset_path():
    citation = RemoteFile("/Fairbanks/citation.txt", 734)

    selected = select_files(
        [citation],
        root=FAIRBANKS_ROOT,
        include=["/Fairbanks/citation.txt"],
    )

    assert selected == [citation]


def test_stat_file_resolves_absolute_path_without_catalog_scan():
    session = CatalogSession()
    client = PubDASClient("transfer-token", session=session)

    citation = client.stat_file("/Fairbanks/citation.txt", root=FAIRBANKS_ROOT)

    assert citation == RemoteFile(
        "/Fairbanks/citation.txt",
        734,
        "2023-01-01 00:00:00+00:00",
    )
    assert len(session.calls) == 1
    assert session.calls[0][0].endswith("/stat")


def test_iter_files_can_stop_before_scanning_subdirectories():
    session = CatalogSession()
    client = PubDASClient("transfer-token", session=session)

    first = next(client.iter_files(FAIRBANKS_ROOT))

    assert first.path == "/Fairbanks/README.txt"
    assert len(session.calls) == 1


def test_iter_files_can_prune_subdirectories():
    session = CatalogSession()
    client = PubDASClient("transfer-token", session=session)

    files = list(
        client.iter_files(FAIRBANKS_ROOT, descend=lambda path: "2017" not in path)
    )

    assert [item.path for item in files] == ["/Fairbanks/README.txt"]
    assert len(session.calls) == 1


def test_download_files_preserves_relative_tree(monkeypatch, tmp_path):
    captured = {}

    def fake_download(url, dest, **kwargs):
        captured["url"] = url
        captured["dest"] = dest
        captured["kwargs"] = kwargs
        return dest

    monkeypatch.setattr("daspull.providers.pubdas.download", fake_download)
    client = PubDASClient(
        "transfer-token",
        https_token="https-token",
        https_base_url="https://data.example",
        session=CatalogSession(),
    )
    remote = RemoteFile("/Fairbanks/2017/shot 01.tdms", 100)

    paths = client.download_files([remote], tmp_path, root=FAIRBANKS_ROOT)

    assert paths == [tmp_path / "2017" / "shot 01.tdms"]
    assert captured["url"] == "https://data.example/Fairbanks/2017/shot%2001.tdms"
    assert captured["kwargs"]["headers"] == {
        "Authorization": "Bearer https-token",
        "X-Requested-With": "XMLHttpRequest",
    }
    assert captured["kwargs"]["expected_size"] == 100


def test_authentication_error_is_clear():
    class UnauthorizedSession:
        def get(self, url, **kwargs):
            return JsonResponse({"message": "token expired"}, status_code=401)

    client = PubDASClient("bad-token", session=UnauthorizedSession())

    try:
        client.list_files(FAIRBANKS_ROOT)
    except PubDASAuthenticationError as exc:
        assert "token expired" in str(exc)
    else:
        raise AssertionError("Expected authentication error")
