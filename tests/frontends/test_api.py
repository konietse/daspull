from datetime import datetime, timezone

import pytest
from helpers import FakeClient

import daspull
from daspull.datasets import DATASETS
from daspull.datasets.acquisition import AcquisitionSelectionError
from daspull.providers.globus_auth import PUBDAS_HTTPS_SCOPE
from daspull.providers.zenodo import ZenodoClient

UTC = timezone.utc

TDMS = "/Fairbanks/Data/tdms/day/data_160812075945.tdms"
LATER_TDMS = "/Fairbanks/Data/tdms/day/data_160812080100.tdms"
SWEEP_CSV = "/Fairbanks/Data/sweeps/day/SRU2_20160812075945.csv"
CITATION = "/Fairbanks/citation.txt"


def fairbanks(paths=(TDMS, SWEEP_CSV, CITATION)):
    client = FakeClient(paths)
    return daspull.open_dataset("fairbanks", client=client), client


def test_open_dataset_rejects_an_unknown_id():
    with pytest.raises(ValueError, match="Unknown dataset 'fairbank'"):
        daspull.open_dataset("fairbank")


def test_list_datasets_matches_the_shipped_configs():
    assert daspull.list_datasets() == list(DATASETS)


def test_describe_datasets_reports_one_row_per_dataset():
    rows = daspull.describe_datasets()

    assert [row["id"] for row in rows] == list(DATASETS)
    assert all(row["provider"].endswith("_https") for row in rows)


def test_list_files_defaults_to_the_primary_file_type():
    dataset, client = fairbanks()

    files = dataset.list_files()

    assert [item.name for item in files] == ["data_160812075945.tdms"]
    assert client.roots == [dataset.spec.primary_root]


def test_list_files_can_include_every_file_type():
    dataset, client = fairbanks()

    files = dataset.list_files(all_file_types=True)

    assert len(files) == 3
    assert client.roots == [dataset.spec.dataset_root]


def test_a_single_glob_string_is_accepted_without_a_list():
    dataset, _ = fairbanks()

    files = dataset.list_files(include="*.csv")

    assert [item.name for item in files] == ["SRU2_20160812075945.csv"]


def test_exclude_filters_out_matching_files():
    dataset, _ = fairbanks()

    files = dataset.list_files(all_file_types=True, exclude=["*.txt", "*.csv"])

    assert [item.name for item in files] == ["data_160812075945.tdms"]


def test_a_date_string_selects_that_whole_utc_day():
    dataset, _ = fairbanks([TDMS, "/Fairbanks/Data/tdms/day/data_160813075945.tdms"])

    files = dataset.list_files(date="2016-08-12")

    assert [item.name for item in files] == ["data_160812075945.tdms"]


def test_a_moment_and_a_buffer_select_a_symmetric_window():
    dataset, _ = fairbanks([TDMS, LATER_TDMS])

    assert [item.name for item in dataset.list_files(date="2016-08-12 08:00:00")] == [
        "data_160812075945.tdms"
    ]
    assert [
        item.name for item in dataset.list_files(date="2016-08-12 08:00:00", buffer=60)
    ] == ["data_160812075945.tdms", "data_160812080100.tdms"]


def test_an_explicit_datetime_interval_is_honoured():
    dataset, _ = fairbanks([TDMS, LATER_TDMS])

    files = dataset.list_files(
        start=datetime(2016, 8, 12, 8, 1, tzinfo=UTC),
        end=datetime(2016, 8, 12, 9, tzinfo=UTC),
    )

    assert [item.name for item in files] == ["data_160812080100.tdms"]


def test_limit_caps_the_selection():
    dataset, _ = fairbanks([TDMS, LATER_TDMS])

    assert len(dataset.list_files(limit=1)) == 1


def test_list_intervals_keeps_a_gap_between_blocks_visible():
    dataset, _ = fairbanks([TDMS, LATER_TDMS])

    assert dataset.list_intervals() == [
        (
            datetime(2016, 8, 12, 7, 59, 45, tzinfo=UTC),
            datetime(2016, 8, 12, 8, 0, 45, tzinfo=UTC),
        ),
        (
            datetime(2016, 8, 12, 8, 1, tzinfo=UTC),
            datetime(2016, 8, 12, 8, 2, tzinfo=UTC),
        ),
    ]


def test_download_refuses_to_take_a_whole_dataset_unasked():
    dataset, client = fairbanks()

    with pytest.raises(ValueError, match="all_files=True"):
        dataset.download()
    assert client.downloaded == []


def test_download_takes_the_whole_primary_catalog_when_asked():
    dataset, client = fairbanks()

    dataset.download(all_files=True)

    assert [item.name for item in client.downloaded] == ["data_160812075945.tdms"]


def test_download_defaults_its_output_dir_to_the_dataset_name():
    dataset, client = fairbanks()

    dataset.download(date="2016-08-12")

    assert client.destinations == ["fairbanks"]


def test_download_writes_below_an_explicit_output_dir(tmp_path):
    dataset, client = fairbanks()

    dataset.download(tmp_path / "out", date="2016-08-12")

    assert client.destinations == [str(tmp_path / "out")]


def test_download_can_reuse_a_selection_from_list_files():
    dataset, client = fairbanks()
    selected = dataset.list_files(all_file_types=True, include="*.csv")

    dataset.download("out", files=selected)

    assert [item.name for item in client.downloaded] == ["SRU2_20160812075945.csv"]


def test_download_rejects_filters_alongside_an_exact_selection():
    dataset, client = fairbanks()
    selected = dataset.list_files()

    with pytest.raises(ValueError, match="already an exact selection"):
        dataset.download("out", files=selected, date="2016-08-12")
    assert client.downloaded == []


def test_module_level_helpers_accept_a_dataset_id():
    client = FakeClient([TDMS, SWEEP_CSV])

    assert [
        item.name
        for item in daspull.list_files("fairbanks", client=client, date="2016-08-12")
    ] == ["data_160812075945.tdms"]
    assert daspull.list_intervals("fairbanks", client=client) == [
        (
            datetime(2016, 8, 12, 7, 59, 45, tzinfo=UTC),
            datetime(2016, 8, 12, 8, 0, 45, tzinfo=UTC),
        )
    ]
    assert daspull.download("fairbanks", "out", client=client, date="2016-08-12")


def test_a_dataset_spec_or_handle_works_wherever_an_id_does():
    client = FakeClient([TDMS])
    handle = daspull.open_dataset(DATASETS["fairbanks"], client=client)

    assert daspull.open_dataset(handle) is handle
    assert len(daspull.list_files(handle)) == 1


def test_a_public_dataset_needs_no_login_and_builds_its_own_client():
    dataset = daspull.open_dataset("das4whale")

    assert dataset.requires_login is False
    assert dataset.provider == "zenodo_https"
    assert isinstance(dataset.client(), ZenodoClient)


def test_a_globus_dataset_reports_that_it_needs_a_login():
    assert daspull.open_dataset("fairbanks").requires_login is True


def test_a_globus_dataset_asks_for_a_data_token_only_to_download(monkeypatch):
    scopes = []

    class FakeStore:
        def access_token(self):
            return "transfer-token"

        def access_token_for_scope(self, scope):
            scopes.append(scope)
            return "https-token"

    monkeypatch.delenv("DASPULL_GLOBUS_TRANSFER_TOKEN", raising=False)
    monkeypatch.delenv("DASPULL_GLOBUS_HTTPS_TOKEN", raising=False)
    monkeypatch.setattr("daspull.providers.TokenStore", FakeStore)
    monkeypatch.setattr(
        "daspull.providers.PubDASClient", lambda *args, **kwargs: FakeClient([TDMS])
    )
    dataset = daspull.open_dataset("fairbanks")

    dataset.list_files(date="2016-08-12")
    assert scopes == []

    dataset.download(all_files=True)
    assert scopes == [PUBDAS_HTTPS_SCOPE]


def test_a_url_target_downloads_directly(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "daspull.api.download_many",
        lambda urls, dest, **kwargs: calls.append((urls, str(dest))) or ["saved"],
    )

    assert daspull.download("https://example.org/file.h5", "data") == ["saved"]
    assert calls == [(["https://example.org/file.h5"], "data")]


def test_a_url_target_rejects_dataset_selection_options():
    with pytest.raises(ValueError, match="cannot be combined with a direct URL"):
        daspull.download("https://example.org/file.h5", "data", date="2016-08-12")


def test_download_url_rejects_anything_that_is_not_a_url():
    with pytest.raises(ValueError, match="not an http"):
        daspull.download_url("fairbanks")


def test_a_multi_configuration_dataset_refuses_an_unspecified_selection():
    client = FakeClient([TDMS])

    with pytest.raises(AcquisitionSelectionError, match="2 different acquisition"):
        daspull.list_files("gordas_2", client=client)


def test_an_acquisition_value_selects_through_the_python_api():
    early = "/GorDAS-2/20230202T221315Z.h5"
    late = "/GorDAS-2/20230203T004204Z.h5"
    dataset = daspull.open_dataset("gordas_2", client=FakeClient([early, late]))

    assert [item.path for item in dataset.list_files(sampling_rate=125)] == [early]
    assert [item.path for item in dataset.list_files(channel_spacing=5.1)] == [late]


def test_an_acquisition_value_is_validated_for_a_single_configuration_dataset():
    with pytest.raises(AcquisitionSelectionError, match="no Fairbanks"):
        daspull.list_files("fairbanks", client=FakeClient([TDMS]), sampling_rate=500)


def test_download_refuses_an_exact_selection_mixed_with_acquisition_values():
    dataset, _ = fairbanks()
    selected = dataset.list_files()

    with pytest.raises(ValueError, match="already an exact selection"):
        dataset.download("out", files=selected, sampling_rate=1000)


def test_login_requires_an_explicit_provider_value():
    with pytest.raises(ValueError, match="Unsupported login provider"):
        daspull.login(provider="not-a-real-provider")


def test_logout_requires_an_explicit_provider_value():
    with pytest.raises(ValueError, match="Unsupported logout provider"):
        daspull.logout(provider="not-a-real-provider")


def test_login_globus_completes_the_pkce_flow_and_saves_tokens(monkeypatch, tmp_path):
    from daspull.providers.globus_auth import NativeLoginFlow

    flow = NativeLoginFlow("https://auth.example/login", "verifier", "state")
    saved = {}

    class FakeStore:
        path = tmp_path / "tokens.json"

        def save_response(self, response):
            saved.update(response)

    monkeypatch.setattr("daspull.api.start_native_login", lambda: flow)
    monkeypatch.setattr("daspull.api.webbrowser.open", lambda url: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "one-time-code")
    monkeypatch.setattr(
        "daspull.api.exchange_authorization_code",
        lambda login_flow, code: {"access_token": code},
    )
    monkeypatch.setattr("daspull.api.TokenStore", FakeStore)

    assert daspull.login(provider="globus") == tmp_path / "tokens.json"
    assert saved == {"access_token": "one-time-code"}


def test_logout_globus_clears_the_token_store(monkeypatch):
    cleared = []
    monkeypatch.setattr(
        "daspull.api.TokenStore",
        lambda: type(
            "FakeStore", (), {"clear": lambda self: cleared.append(True) or True}
        )(),
    )

    assert daspull.logout(provider="globus") is True
    assert cleared == [True]
