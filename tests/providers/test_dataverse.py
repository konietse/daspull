import requests

from daspull.providers.dataverse import DataverseClient, DataverseError

BASE_URL = "https://dataverse.no"
PERSISTENT_ID = "doi:10.18710/VPRD2H"
DATASET_ROOT = "/DAS4Microseism/"


class JsonResponse:
    def __init__(self, payload, *, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class CatalogSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        assert url == f"{BASE_URL}/api/datasets/:persistentId/"
        assert kwargs["params"] == {"persistentId": PERSISTENT_ID}
        return JsonResponse(
            {
                "data": {
                    "latestVersion": {
                        "files": [
                            {
                                "directoryLabel": "Data/Hourly",
                                "dataFile": {
                                    "id": 117961,
                                    "filename": (
                                        "20200705_000005_ch01050_to_ch18000_"
                                        "rsamp20ms_L300s_hourly_nogeom.mat"
                                    ),
                                    "filesize": 366944840,
                                    "checksum": {
                                        "type": "MD5",
                                        "value": "abc123",
                                    },
                                    "publicationDate": "2022-02-28",
                                },
                            },
                            {
                                "dataFile": {
                                    "id": 118278,
                                    "filename": "00_README.txt",
                                    "filesize": 13671,
                                    "checksum": {
                                        "type": "MD5",
                                        "value": "def456",
                                    },
                                },
                            },
                        ]
                    }
                }
            }
        )


def make_client(session=None):
    return DataverseClient(
        BASE_URL, PERSISTENT_ID, DATASET_ROOT, session=session or CatalogSession()
    )


def test_iter_files_synthesizes_paths_from_directory_label_and_filename():
    client = make_client()

    files = client.list_files(DATASET_ROOT)

    assert [item.path for item in files] == [
        "/DAS4Microseism/00_README.txt",
        (
            "/DAS4Microseism/Data/Hourly/20200705_000005_ch01050_to_ch18000_"
            "rsamp20ms_L300s_hourly_nogeom.mat"
        ),
    ]
    assert files[1].size == 366944840
    assert files[1].checksum == "abc123"


def test_iter_files_filters_by_root():
    client = make_client()

    files = list(client.iter_files("/DAS4Microseism/Data/"))

    assert [item.name for item in files] == [
        "20200705_000005_ch01050_to_ch18000_rsamp20ms_L300s_hourly_nogeom.mat"
    ]


def test_descend_is_accepted_but_has_no_effect():
    client = make_client()

    files = list(client.iter_files(DATASET_ROOT, descend=lambda path: False))

    assert len(files) == 2


def test_catalog_is_fetched_only_once_across_calls():
    session = CatalogSession()
    client = make_client(session)

    client.list_files(DATASET_ROOT)
    client.stat_file("00_README.txt", root=DATASET_ROOT)
    list(client.iter_files(DATASET_ROOT))

    assert len(session.calls) == 1


def test_stat_file_resolves_a_root_relative_literal_path():
    client = make_client()

    remote = client.stat_file("00_README.txt", root=DATASET_ROOT)

    assert remote.path == "/DAS4Microseism/00_README.txt"
    assert remote.size == 13671


def test_stat_file_raises_for_an_unknown_path():
    client = make_client()

    try:
        client.stat_file("nonexistent.txt", root=DATASET_ROOT)
    except DataverseError as exc:
        assert "nonexistent.txt" in str(exc)
    else:
        raise AssertionError("Expected DataverseError")


def test_download_files_uses_the_datafile_id_and_preserves_relative_tree(
    monkeypatch, tmp_path
):
    captured = {}

    def fake_download(url, dest, **kwargs):
        captured["url"] = url
        captured["dest"] = dest
        captured["kwargs"] = kwargs
        return dest

    monkeypatch.setattr("daspull.providers.dataverse.download", fake_download)
    client = make_client()
    remote = client.stat_file(
        "Data/Hourly/20200705_000005_ch01050_to_ch18000_rsamp20ms_L300s_hourly_nogeom.mat",
        root=DATASET_ROOT,
    )

    paths = client.download_files([remote], tmp_path, root=DATASET_ROOT)

    assert paths == [
        tmp_path
        / "Data"
        / "Hourly"
        / "20200705_000005_ch01050_to_ch18000_rsamp20ms_L300s_hourly_nogeom.mat"
    ]
    assert captured["url"] == f"{BASE_URL}/api/access/datafile/117961"
    assert captured["kwargs"]["checksum"] == "abc123"
    assert captured["kwargs"]["checksum_algo"] == "md5"
    assert captured["kwargs"]["expected_size"] == 366944840


def test_download_file_wraps_a_forbidden_response_as_a_clear_error(
    monkeypatch, tmp_path
):
    def fake_download(url, dest, **kwargs):
        error = requests.HTTPError("HTTP 403")
        error.response = JsonResponse({}, status_code=403)
        raise error

    monkeypatch.setattr("daspull.providers.dataverse.download", fake_download)
    client = make_client()
    remote = client.stat_file("00_README.txt", root=DATASET_ROOT)

    try:
        client.download_file(remote, tmp_path)
    except DataverseError as exc:
        assert "00_README.txt" in str(exc)
    else:
        raise AssertionError("Expected DataverseError")
