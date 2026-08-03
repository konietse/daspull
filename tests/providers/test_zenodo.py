import requests

from daspull.providers.zenodo import ZenodoClient, ZenodoError

BASE_URL = "https://zenodo.org"
RECORD_ID = "5823343"
DATASET_ROOT = "/DAS4Whale/"


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


class RecordSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        assert url == f"{BASE_URL}/api/records/{RECORD_ID}"
        return JsonResponse(
            {
                "metadata": {"publication_date": "2022-01-10"},
                "files": [
                    {
                        "key": (
                            "20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat"
                        ),
                        "size": 1033292856,
                        "checksum": "md5:41d7296eb2e0e1c8579b9de1d908aa35",
                        "links": {
                            "self": (
                                f"{BASE_URL}/api/records/{RECORD_ID}/files/"
                                "20200627_052441_ch08751_to_ch10000_"
                                "whale_raw_L160s.mat/content"
                            )
                        },
                    },
                    {
                        "key": (
                            "20200716_154302_ch24001_to_ch25000_whale_raw_L720s.mat"
                        ),
                        "size": 3719802920,
                        "checksum": "md5:e111af456fd97cec1780b5d2440d5eff",
                        "links": {
                            "self": (
                                f"{BASE_URL}/api/records/{RECORD_ID}/files/"
                                "20200716_154302_ch24001_to_ch25000_"
                                "whale_raw_L720s.mat/content"
                            )
                        },
                    },
                ],
            }
        )


def make_client(session=None):
    return ZenodoClient(
        BASE_URL, RECORD_ID, DATASET_ROOT, session=session or RecordSession()
    )


def test_iter_files_synthesizes_paths_directly_below_root():
    client = make_client()

    files = client.list_files(DATASET_ROOT)

    assert [item.path for item in files] == [
        "/DAS4Whale/20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat",
        "/DAS4Whale/20200716_154302_ch24001_to_ch25000_whale_raw_L720s.mat",
    ]
    assert files[0].size == 1033292856
    assert files[0].checksum == "41d7296eb2e0e1c8579b9de1d908aa35"
    assert files[0].last_modified == "2022-01-10"


def test_descend_is_accepted_but_has_no_effect():
    client = make_client()

    files = list(client.iter_files(DATASET_ROOT, descend=lambda path: False))

    assert len(files) == 2


def test_catalog_is_fetched_only_once_across_calls():
    session = RecordSession()
    client = make_client(session)

    client.list_files(DATASET_ROOT)
    client.stat_file(
        "20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat",
        root=DATASET_ROOT,
    )
    list(client.iter_files(DATASET_ROOT))

    assert len(session.calls) == 1


def test_stat_file_resolves_a_root_relative_literal_path():
    client = make_client()

    remote = client.stat_file(
        "20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat",
        root=DATASET_ROOT,
    )

    assert (
        remote.path
        == "/DAS4Whale/20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat"
    )
    assert remote.size == 1033292856


def test_stat_file_raises_for_an_unknown_path():
    client = make_client()

    try:
        client.stat_file("nonexistent.mat", root=DATASET_ROOT)
    except ZenodoError as exc:
        assert "nonexistent.mat" in str(exc)
    else:
        raise AssertionError("Expected ZenodoError")


def test_download_files_uses_the_files_link_directly(monkeypatch, tmp_path):
    captured = {}

    def fake_download(url, dest, **kwargs):
        captured["url"] = url
        captured["dest"] = dest
        captured["kwargs"] = kwargs
        return dest

    monkeypatch.setattr("daspull.providers.zenodo.download", fake_download)
    client = make_client()
    remote = client.stat_file(
        "20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat",
        root=DATASET_ROOT,
    )

    paths = client.download_files([remote], tmp_path, root=DATASET_ROOT)

    assert paths == [
        tmp_path / "20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat"
    ]
    assert captured["url"] == (
        f"{BASE_URL}/api/records/{RECORD_ID}/files/"
        "20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat/content"
    )
    assert captured["kwargs"]["checksum"] == "41d7296eb2e0e1c8579b9de1d908aa35"
    assert captured["kwargs"]["checksum_algo"] == "md5"
    assert captured["kwargs"]["expected_size"] == 1033292856


def test_download_file_wraps_a_forbidden_response_as_a_clear_error(
    monkeypatch, tmp_path
):
    def fake_download(url, dest, **kwargs):
        error = requests.HTTPError("HTTP 403")
        error.response = JsonResponse({}, status_code=403)
        raise error

    monkeypatch.setattr("daspull.providers.zenodo.download", fake_download)
    client = make_client()
    remote = client.stat_file(
        "20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat",
        root=DATASET_ROOT,
    )

    try:
        client.download_file(remote, tmp_path)
    except ZenodoError as exc:
        assert "20200627_052441_ch08751_to_ch10000_whale_raw_L160s.mat" in str(exc)
    else:
        raise AssertionError("Expected ZenodoError")
