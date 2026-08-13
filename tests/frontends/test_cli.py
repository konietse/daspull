import pytest
from helpers import install_fake_globus_client

from daspull.catalog import RemoteFile
from daspull.cli import build_dataset_parser, main
from daspull.datasets import DATASETS
from daspull.providers.globus_auth import NativeLoginFlow

FAIRBANKS = DATASETS["fairbanks"]
FORESEE = DATASETS["foresee"]


def test_login_requires_an_explicit_provider():
    with pytest.raises(SystemExit) as exc:
        main(["login", "--no-browser"])

    assert exc.value.code == 2


def test_logout_requires_an_explicit_provider():
    with pytest.raises(SystemExit) as exc:
        main(["logout"])

    assert exc.value.code == 2


def test_globus_login_falls_back_when_no_local_browser(monkeypatch, tmp_path):
    flow = NativeLoginFlow("https://auth.example/login", "verifier", "state")
    saved = {}

    class FakeStore:
        path = tmp_path / "tokens.json"

        def save_response(self, response):
            saved.update(response)

    def browser_unavailable(url):
        raise __import__("webbrowser").Error("no browser")

    monkeypatch.setattr("daspull.api.start_native_login", lambda: flow)
    monkeypatch.setattr("daspull.api.webbrowser.open", browser_unavailable)
    monkeypatch.setattr("builtins.input", lambda prompt: "one-time-code")
    monkeypatch.setattr(
        "daspull.api.exchange_authorization_code",
        lambda login_flow, code: {"access_token": code},
    )
    monkeypatch.setattr("daspull.api.TokenStore", FakeStore)

    assert main(["login", "--globus"]) == 0
    assert saved == {"access_token": "one-time-code"}


def test_fairbanks_parser_accepts_unquoted_utc_range():
    args = build_dataset_parser(FAIRBANKS).parse_args(
        [
            "--start",
            "2016-08-05",
            "07:31:15",
            "--end",
            "2016-10-03",
            "10:09:21",
        ]
    )

    assert args.start == ["2016-08-05", "07:31:15"]
    assert args.end == ["2016-10-03", "10:09:21"]


def test_fairbanks_time_range_requires_both_boundaries():
    with pytest.raises(SystemExit) as exc:
        main(["fairbanks", "--start", "2016-08-05", "07:31:15"])

    assert exc.value.code == 2


def test_fairbanks_time_range_rejects_reversed_interval():
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "fairbanks",
                "--start",
                "2016-08-06",
                "00:00:00",
                "--end",
                "2016-08-05",
                "00:00:00",
            ]
        )

    assert exc.value.code == 2


def test_fairbanks_date_month_selects_the_whole_utc_month(monkeypatch):
    files = [
        RemoteFile("/Fairbanks/Data/tdms/day/data_160805073115.tdms", 100),
        RemoteFile("/Fairbanks/Data/tdms/day/data_160905073115.tdms", 100),
    ]
    client = install_fake_globus_client(monkeypatch, files)

    assert main(["fairbanks", "--date", "2016-08"]) == 0
    assert [item.name for item in client.downloaded] == ["data_160805073115.tdms"]


def test_fairbanks_date_rejects_an_invalid_calendar_value():
    with pytest.raises(SystemExit) as exc:
        main(["fairbanks", "--date", "2016-13", "--dry-run"])

    assert exc.value.code == 2


def test_fairbanks_date_with_time_and_buffer_selects_symmetric_window():
    args = build_dataset_parser(FAIRBANKS).parse_args(
        [
            "--date",
            "2016-08-12",
            "08:00:00",
            "--buffer",
            "30",
            "--dry-run",
        ]
    )

    assert args.date == ["2016-08-12", "08:00:00"]
    assert args.buffer == 30


def test_fairbanks_date_instant_without_buffer_defaults_to_zero(monkeypatch):
    files = [
        RemoteFile("/Fairbanks/Data/tdms/day/data_160812075945.tdms", 100),
        RemoteFile("/Fairbanks/Data/tdms/day/data_160812080100.tdms", 100),
    ]
    client = install_fake_globus_client(monkeypatch, files)

    assert (
        main(
            [
                "fairbanks",
                "--date",
                "2016-08-12",
                "08:00:00",
                "--all",
            ]
        )
        == 0
    )
    assert [item.name for item in client.downloaded] == ["data_160812075945.tdms"]


def test_fairbanks_date_instant_with_buffer_widens_the_window(monkeypatch):
    files = [
        RemoteFile("/Fairbanks/Data/tdms/day/data_160812075945.tdms", 100),
        RemoteFile("/Fairbanks/Data/tdms/day/data_160812080100.tdms", 100),
    ]
    client = install_fake_globus_client(monkeypatch, files)

    assert (
        main(
            [
                "fairbanks",
                "--date",
                "2016-08-12",
                "08:00:00",
                "--buffer",
                "60",
                "--all",
            ]
        )
        == 0
    )
    assert [item.name for item in client.downloaded] == [
        "data_160812075945.tdms",
        "data_160812080100.tdms",
    ]


def test_fairbanks_date_instant_may_arrive_as_one_quoted_argument(monkeypatch):
    files = [
        RemoteFile("/Fairbanks/Data/tdms/day/data_160812075945.tdms", 100),
        RemoteFile("/Fairbanks/Data/tdms/day/data_160812080100.tdms", 100),
    ]
    client = install_fake_globus_client(monkeypatch, files)

    assert (
        main(
            [
                "fairbanks",
                "--date",
                "2016-08-12 08:00:00",
                "--buffer",
                "60",
                "--all",
            ]
        )
        == 0
    )
    assert [item.name for item in client.downloaded] == [
        "data_160812075945.tdms",
        "data_160812080100.tdms",
    ]


def test_fairbanks_buffer_requires_an_exact_date_instant():
    with pytest.raises(SystemExit) as exc:
        main(["fairbanks", "--date", "2016-08-12", "--buffer", "30", "--dry-run"])

    assert exc.value.code == 2


def test_fairbanks_date_rejects_more_than_a_date_and_a_time():
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "fairbanks",
                "--date",
                "2016-08-12",
                "08:00:00",
                "extra",
                "--dry-run",
            ]
        )

    assert exc.value.code == 2


def test_fairbanks_date_cannot_be_combined_with_explicit_range():
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "fairbanks",
                "--date",
                "2016-08",
                "--start",
                "2016-08-01",
                "00:00:00",
                "--end",
                "2016-09-01",
                "00:00:00",
            ]
        )

    assert exc.value.code == 2


def test_fairbanks_download_defaults_to_primary_tdms_files(monkeypatch):
    files = [
        RemoteFile("/Fairbanks/Data/tdms/day/data_160805073115.tdms", 100),
        RemoteFile("/Fairbanks/Data/sweeps/day/SRU2_20160805073218.csv", 50),
        RemoteFile("/Fairbanks/citation.txt", 10),
    ]
    client = install_fake_globus_client(monkeypatch, files)

    assert main(["fairbanks", "--all"]) == 0
    assert [item.name for item in client.downloaded] == ["data_160805073115.tdms"]
    assert client.roots == [FAIRBANKS.primary_root]


def test_fairbanks_explicit_include_overrides_primary_file_type(monkeypatch):
    files = [
        RemoteFile("/Fairbanks/Data/tdms/day/data_160805073115.tdms", 100),
        RemoteFile("/Fairbanks/Data/sweeps/day/SRU2_20160805073218.csv", 50),
    ]
    client = install_fake_globus_client(monkeypatch, files)

    assert main(["fairbanks", "--include", "*.csv"]) == 0
    assert [item.name for item in client.downloaded] == ["SRU2_20160805073218.csv"]


def test_fairbanks_lists_continuous_tdms_intervals(monkeypatch, capsys):
    files = [
        RemoteFile("/Fairbanks/Data/tdms/day/data_160805073215.tdms", 100),
        RemoteFile("/Fairbanks/Data/tdms/day/data_160805073115.tdms", 100),
        RemoteFile("/Fairbanks/Data/tdms/day/data_160805073416.tdms", 100),
    ]
    client = install_fake_globus_client(monkeypatch, files)

    assert main(["fairbanks", "--list-intervals"]) == 0

    captured = capsys.readouterr()
    assert client.roots == [FAIRBANKS.primary_root]
    assert captured.out.splitlines() == [
        "START UTC (inclusive)    END UTC (exclusive)",
        "2016-08-05 07:31:15    2016-08-05 07:33:15",
        "2016-08-05 07:34:16    2016-08-05 07:35:16",
        "2 interval(s)",
    ]


def test_fairbanks_interval_listing_rejects_limit():
    with pytest.raises(SystemExit) as exc:
        main(["fairbanks", "--list-intervals", "--limit", "1"])

    assert exc.value.code == 2


def test_dataset_parser_leaves_output_dir_unset_by_default():
    args = build_dataset_parser(FORESEE).parse_args(["--dry-run"])

    assert args.output_dir is None


def test_foresee_download_defaults_to_primary_hdf5_files(monkeypatch):
    files = [
        RemoteFile("/FORESEE/Data/201904/FORESEE_UTC_20190404_194804.hdf5", 100),
        RemoteFile("/FORESEE/readme.txt", 10),
    ]
    client = install_fake_globus_client(monkeypatch, files)

    assert main(["foresee", "--all"]) == 0
    assert [item.name for item in client.downloaded] == [
        "FORESEE_UTC_20190404_194804.hdf5"
    ]
    assert client.roots == [FORESEE.primary_root]


def test_foresee_lists_continuous_hdf5_intervals(monkeypatch, capsys):
    files = [
        RemoteFile("/FORESEE/Data/201904/FORESEE_UTC_20190404_195804.hdf5", 100),
        RemoteFile("/FORESEE/Data/201904/FORESEE_UTC_20190404_194804.hdf5", 100),
        RemoteFile("/FORESEE/Data/201904/FORESEE_UTC_20190405_185804.hdf5", 100),
    ]
    client = install_fake_globus_client(monkeypatch, files)

    assert main(["foresee", "--list-intervals"]) == 0

    captured = capsys.readouterr()
    assert client.roots == [FORESEE.primary_root]
    assert captured.out.splitlines() == [
        "START UTC (inclusive)    END UTC (exclusive)",
        "2019-04-04 19:48:04    2019-04-04 20:08:04",
        "2019-04-05 18:58:04    2019-04-05 19:08:04",
        "2 interval(s)",
    ]


def test_list_intervals_with_output_dir_also_writes_a_csv(
    monkeypatch, capsys, tmp_path
):
    files = [
        RemoteFile("/FORESEE/Data/201904/FORESEE_UTC_20190404_195804.hdf5", 100),
        RemoteFile("/FORESEE/Data/201904/FORESEE_UTC_20190404_194804.hdf5", 100),
    ]
    install_fake_globus_client(monkeypatch, files)
    dest = tmp_path / "tmp"

    assert main(["foresee", "--list-intervals", "-o", str(dest)]) == 0

    csv_path = dest / "foresee_intervals.csv"
    assert csv_path.read_text().splitlines() == [
        "start_utc,end_utc",
        "2019-04-04 19:48:04,2019-04-04 20:08:04",
    ]
    assert f"Saved: {csv_path}" in capsys.readouterr().out


SGY_ROOT = "/Stanford-3-ODH4/Data/ODH4-2017-SEGY"
FIFTY_HZ = f"{SGY_ROOT}/SGY_Stanford_Permanent_DT37"
HUNDRED_HZ = f"{SGY_ROOT}/SGY_Stanford_Permanent_DT37_100Hz"


def test_a_multi_configuration_dataset_refuses_an_unspecified_selection(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["stanford_3", "--list"])

    assert exc.value.code == 2
    assert "4 different acquisition configurations" in capsys.readouterr().err


def test_an_acquisition_value_that_matches_nothing_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["stanford_3", "--sampling-rate", "37", "--list"])

    assert exc.value.code == 2
    assert "no Stanford-3 acquisition configuration" in capsys.readouterr().err


def test_an_acquisition_selection_keeps_only_its_own_subtree(monkeypatch):
    files = [
        RemoteFile(f"{FIFTY_HZ}/cbt_processed_20171006_223449.533+0000.sgy", 18738240),
        RemoteFile(
            f"{HUNDRED_HZ}/cbt_processed_20171009_175814.479+0000.sgy", 37398240
        ),
        RemoteFile("/Stanford-3-ODH4/Stanford-1-Campus-geometry.csv", 28397),
    ]
    client = install_fake_globus_client(monkeypatch, files)

    assert (
        main(
            [
                "stanford_3",
                "--sampling-rate",
                "50",
                "--include",
                "*.sgy",
                "--include",
                "*.csv",
            ]
        )
        == 0
    )

    downloaded = [item.path for item in client.downloaded]
    assert f"{FIFTY_HZ}/cbt_processed_20171006_223449.533+0000.sgy" in downloaded
    assert f"{HUNDRED_HZ}/cbt_processed_20171009_175814.479+0000.sgy" not in downloaded
    # a file that is not a recording is never filtered out by an acquisition
    # selection -- the geometry table is needed whichever settings you picked
    assert "/Stanford-3-ODH4/Stanford-1-Campus-geometry.csv" in downloaded


def test_an_acquisition_selection_prunes_the_other_subtrees(monkeypatch):
    client = install_fake_globus_client(monkeypatch, [])

    assert main(["stanford_3", "--gauge", "2", "--all"]) == 1

    descend = client.descend
    assert descend is not None
    assert descend(f"{SGY_ROOT}/SGY_Stanford_Permanent_DT37_100_Hz_2m_gauge/")
    assert not descend(f"{FIFTY_HZ}/")
    assert not descend(f"{HUNDRED_HZ}/")


def test_a_selection_spanning_several_configurations_is_refused(monkeypatch, capsys):
    client = install_fake_globus_client(monkeypatch, [])

    with pytest.raises(SystemExit) as exc:
        main(["stanford_3", "--sampling-rate", "100", "--all"])

    assert exc.value.code == 2
    assert (
        "still spans 3 different acquisition configurations" in capsys.readouterr().err
    )
    assert client.roots == []


def test_a_selection_matching_only_duplicate_settings_is_not_refused(
    monkeypatch, capsys
):
    client = install_fake_globus_client(monkeypatch, [])

    assert (
        main(["stanford_3", "--sampling-rate", "100", "--gauge", "7.14", "--all"]) == 1
    )

    assert "spans" not in capsys.readouterr().err
    assert client.roots == [DATASETS["stanford_3"].primary_root]


def test_a_single_configuration_dataset_validates_the_value(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["fairbanks", "--sampling-rate", "500", "--all"])

    assert exc.value.code == 2
    assert "no Fairbanks acquisition configuration" in capsys.readouterr().err


def test_a_single_configuration_dataset_accepts_its_own_value(monkeypatch):
    files = [RemoteFile("/Fairbanks/Data/tdms/day/data_160805073115.tdms", 100)]
    client = install_fake_globus_client(monkeypatch, files)

    assert main(["fairbanks", "--sampling-rate", "1000", "--all"]) == 0
    assert len(client.downloaded) == 1
