import requests

from daspull.providers.s3 import S3Client, S3Error

BASE_URL = "https://example-bucket.s3.amazonaws.com"
PREFIX = "data/porotomo/DASH/"
DATASET_ROOT = "/PoroTomo_H/"

NS = "http://s3.amazonaws.com/doc/2006-03-01/"


def _listing_xml(
    prefix, *, common_prefixes=(), contents=(), truncated=False, token=None
):
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<ListBucketResult xmlns="{NS}">',
        f"<Prefix>{prefix}</Prefix>",
        f"<IsTruncated>{'true' if truncated else 'false'}</IsTruncated>",
    ]
    if truncated:
        parts.append(f"<NextContinuationToken>{token}</NextContinuationToken>")
    for key, size, etag in contents:
        parts.append(
            f"<Contents><Key>{key}</Key><Size>{size}</Size>"
            f"<ETag>&quot;{etag}&quot;</ETag>"
            f"<LastModified>2020-01-01T00:00:00.000Z</LastModified></Contents>"
        )
    for cp in common_prefixes:
        parts.append(f"<CommonPrefixes><Prefix>{cp}</Prefix></CommonPrefixes>")
    parts.append("</ListBucketResult>")
    return "".join(parts).encode("utf-8")


class FakeResponse:
    def __init__(self, content=b"", *, status_code=200, headers=None):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error


class BucketSession:
    def __init__(self):
        self.calls = []
        self.page_two_served = False

    def get(self, url, **kwargs):
        params = kwargs.get("params") or {}
        self.calls.append((url, params))
        assert url == f"{BASE_URL}/"
        prefix = params["prefix"]

        if prefix == PREFIX:
            return FakeResponse(
                _listing_xml(
                    prefix,
                    common_prefixes=[
                        f"{PREFIX}20160311/",
                        f"{PREFIX}20160312/",
                    ],
                )
            )
        if prefix == f"{PREFIX}20160311/":
            if "continuation-token" not in params:
                return FakeResponse(
                    _listing_xml(
                        prefix,
                        contents=[
                            (
                                f"{prefix}PoroTomo_iDAS16043_160311164618.h5",
                                1046784080,
                                "abcdef0123456789abcdef0123456789",
                            )
                        ],
                        truncated=True,
                        token="page2token",
                    )
                )
            self.page_two_served = True
            return FakeResponse(
                _listing_xml(
                    prefix,
                    contents=[
                        (
                            f"{prefix}PoroTomo_iDAS16043_160311164648.h5",
                            1046784080,
                            "multipart-etag-does-not-look-like-md5-125",
                        )
                    ],
                )
            )
        if prefix == f"{PREFIX}20160312/":
            return FakeResponse(
                _listing_xml(
                    prefix,
                    contents=[
                        (
                            f"{prefix}PoroTomo_iDAS16043_160312000018.h5",
                            1046784080,
                            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        )
                    ],
                )
            )
        raise AssertionError(f"Unexpected prefix requested: {prefix}")

    def head(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url == f"{BASE_URL}/{PREFIX}20160311/PoroTomo_iDAS16043_160311164618.h5":
            return FakeResponse(
                status_code=200,
                headers={
                    "Content-Length": "1046784080",
                    "ETag": '"abcdef0123456789abcdef0123456789"',
                    "Last-Modified": "Wed, 05 Sep 2024 18:05:13 GMT",
                },
            )
        return FakeResponse(status_code=404)


def make_client(session=None):
    return S3Client(BASE_URL, PREFIX, DATASET_ROOT, session=session or BucketSession())


def test_iter_files_walks_the_real_directory_tree():
    client = make_client()

    files = client.list_files(DATASET_ROOT)

    assert [item.path for item in files] == [
        "/PoroTomo_H/20160311/PoroTomo_iDAS16043_160311164618.h5",
        "/PoroTomo_H/20160311/PoroTomo_iDAS16043_160311164648.h5",
        "/PoroTomo_H/20160312/PoroTomo_iDAS16043_160312000018.h5",
    ]
    assert files[0].size == 1046784080


def test_pagination_is_followed_via_continuation_token():
    session = BucketSession()
    client = make_client(session)

    list(client.iter_files(f"{DATASET_ROOT}20160311/"))

    assert session.page_two_served


def test_descend_genuinely_prunes_a_real_subtree():
    client = make_client()

    files = list(
        client.iter_files(DATASET_ROOT, descend=lambda path: "20160311" in path)
    )

    assert [item.name for item in files] == [
        "PoroTomo_iDAS16043_160311164618.h5",
        "PoroTomo_iDAS16043_160311164648.h5",
    ]


def test_single_part_etag_is_used_as_an_md5_checksum():
    client = make_client()

    files = list(client.iter_files(f"{DATASET_ROOT}20160312/"))

    assert files[0].checksum == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def test_multipart_etag_is_not_used_as_a_checksum():
    client = make_client()

    files = list(client.iter_files(f"{DATASET_ROOT}20160311/"))

    assert files[1].checksum is None


def test_stat_file_resolves_via_head_request():
    client = make_client()

    remote = client.stat_file(
        "20160311/PoroTomo_iDAS16043_160311164618.h5", root=DATASET_ROOT
    )

    assert remote.path == "/PoroTomo_H/20160311/PoroTomo_iDAS16043_160311164618.h5"
    assert remote.size == 1046784080
    assert remote.checksum == "abcdef0123456789abcdef0123456789"


def test_stat_file_raises_for_a_missing_object():
    client = make_client()

    try:
        client.stat_file("20160311/nonexistent.h5", root=DATASET_ROOT)
    except S3Error as exc:
        assert "nonexistent.h5" in str(exc)
    else:
        raise AssertionError("Expected S3Error")


def test_download_files_maps_the_virtual_path_to_the_real_key(monkeypatch, tmp_path):
    captured = {}

    def fake_download(url, dest, **kwargs):
        captured["url"] = url
        captured["dest"] = dest
        captured["kwargs"] = kwargs
        return dest

    monkeypatch.setattr("daspull.providers.s3.download", fake_download)
    client = make_client()
    remote = client.stat_file(
        "20160311/PoroTomo_iDAS16043_160311164618.h5", root=DATASET_ROOT
    )

    paths = client.download_files([remote], tmp_path, root=DATASET_ROOT)

    assert paths == [tmp_path / "20160311" / "PoroTomo_iDAS16043_160311164618.h5"]
    assert captured["url"] == (
        f"{BASE_URL}/{PREFIX}20160311/PoroTomo_iDAS16043_160311164618.h5"
    )
    assert captured["kwargs"]["checksum"] == "abcdef0123456789abcdef0123456789"
    assert captured["kwargs"]["checksum_algo"] == "md5"
    assert captured["kwargs"]["expected_size"] == 1046784080
