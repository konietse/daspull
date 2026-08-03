from __future__ import annotations

import webbrowser
from collections.abc import Iterable, Sequence
from datetime import date as date_type
from datetime import datetime
from pathlib import Path

from .catalog import RemoteFile
from .client import DatasetClient
from .datasets import (
    DATASETS,
    DatasetSpec,
    continuous_dataset_intervals,
    download_dataset_files,
    select_dataset_files,
)
from .datasets.acquisition import AcquisitionConfig
from .datasets.layout import Interval
from .download import download_many
from .providers import build_client, provider_type, requires_login
from .providers.globus_auth import (
    GLOBUS_CLIENT_ID,
    TokenStore,
    exchange_authorization_code,
    start_native_login,
)
from .timerange import resolve_time_range

_LOGIN_PROVIDERS = ("globus",)

_URL_SCHEMES = ("http://", "https://")

_SELECTION_HINT = (
    "refusing to download a whole dataset by accident: pass include=, "
    "date=, start=/end=, or all_files=True"
)


class Dataset:
    """One dataset, ready to browse and download.

    Wraps a :class:`~daspull.datasets.DatasetSpec` together with the access
    client for its provider, which is built on first use (and, for a Globus
    dataset, upgraded from a browse-only token to a data-access one the first
    time something is actually downloaded).
    """

    def __init__(
        self,
        spec: DatasetSpec,
        *,
        client: DatasetClient | None = None,
        https_base_url: str | None = None,
    ) -> None:
        self.spec = spec
        self._https_base_url = https_base_url
        self._client = client
        # A caller-supplied client is used as-is; so is any client for a
        # provider that needs no login, since browsing and downloading it use
        # exactly the same (absent) credentials.
        self._client_can_download = client is not None or not requires_login(spec)

    @property
    def name(self) -> str:
        """The dataset id, e.g. ``"das4microseism"``."""
        return self.spec.name

    @property
    def display_name(self) -> str:
        """The dataset's human-readable name, e.g. ``"DAS4Microseism"``."""
        return self.spec.display_name

    @property
    def summary(self) -> str:
        """One-line description of the dataset."""
        return self.spec.summary

    @property
    def data_format(self) -> str:
        """The primary file format, e.g. ``"HDF5"``."""
        return self.spec.block_label

    @property
    def provider(self) -> str:
        """The access type backing this dataset, e.g. ``"s3_https"``."""
        return provider_type(self.spec)

    @property
    def requires_login(self) -> bool:
        """Whether `daspull login` is needed before this dataset can be read."""
        return requires_login(self.spec)

    @property
    def configurations(self) -> tuple[AcquisitionConfig, ...]:
        """Every acquisition configuration this dataset recorded with.

        More than one means ``sampling_rate=``/``channel_spacing=``/
        ``gauge_length=`` is required before any files can be selected; each
        entry's ``describe()`` is the one-line summary the CLI prints.
        """
        return self.spec.configurations

    @property
    def metadata(self) -> dict:
        """The dataset's full parsed config (provenance, acquisition, ...)."""
        return self.spec.metadata

    def client(self, *, for_download: bool = False) -> DatasetClient:
        """Return this dataset's access client, building it on first use."""
        if self._client is not None and (self._client_can_download or not for_download):
            return self._client
        self._client = build_client(
            self.spec,
            catalog_only=not for_download,
            https_base_url=self._https_base_url,
        )
        self._client_can_download = for_download or not self.requires_login
        return self._client

    def list_files(
        self,
        *,
        include: str | Sequence[str] | None = None,
        exclude: str | Sequence[str] | None = None,
        date: str | datetime | date_type | None = None,
        start: str | datetime | date_type | None = None,
        end: str | datetime | date_type | None = None,
        buffer: float = 0,
        limit: int | None = None,
        all_file_types: bool = False,
        sampling_rate: float | None = None,
        channel_spacing: float | None = None,
        gauge_length: float | None = None,
    ) -> list[RemoteFile]:
        """List the remote files this selection matches (the CLI's ``--list``)."""
        range_start, range_end = resolve_time_range(
            date=date, start=start, end=end, buffer=buffer
        )
        return select_dataset_files(
            self.client(),
            self.spec,
            include=_patterns(include),
            exclude=_patterns(exclude),
            start=range_start,
            end=range_end,
            limit=limit,
            include_all_file_types=all_file_types,
            configurations=self.spec.acquisition_configs(
                sampling_rate=sampling_rate,
                channel_spacing=channel_spacing,
                gauge_length=gauge_length,
            ),
        )

    def list_intervals(
        self,
        *,
        include: str | Sequence[str] | None = None,
        exclude: str | Sequence[str] | None = None,
        date: str | datetime | date_type | None = None,
        start: str | datetime | date_type | None = None,
        end: str | datetime | date_type | None = None,
        buffer: float = 0,
        sampling_rate: float | None = None,
        channel_spacing: float | None = None,
        gauge_length: float | None = None,
    ) -> list[Interval]:
        """Return continuous UTC coverage intervals (``--list-intervals``)."""
        range_start, range_end = resolve_time_range(
            date=date, start=start, end=end, buffer=buffer
        )
        return continuous_dataset_intervals(
            self.client(),
            self.spec,
            include=_patterns(include),
            exclude=_patterns(exclude),
            start=range_start,
            end=range_end,
            configurations=self.spec.acquisition_configs(
                sampling_rate=sampling_rate,
                channel_spacing=channel_spacing,
                gauge_length=gauge_length,
            ),
        )

    def download(
        self,
        out: str | Path | None = None,
        *,
        files: Iterable[RemoteFile] | None = None,
        include: str | Sequence[str] | None = None,
        exclude: str | Sequence[str] | None = None,
        date: str | datetime | date_type | None = None,
        start: str | datetime | date_type | None = None,
        end: str | datetime | date_type | None = None,
        buffer: float = 0,
        limit: int | None = None,
        all_files: bool = False,
        all_file_types: bool = False,
        sampling_rate: float | None = None,
        channel_spacing: float | None = None,
        gauge_length: float | None = None,
        overwrite: bool = False,
    ) -> list[Path]:
        """Download the selected files, preserving their tree below *out*.

        Downloading a dataset's entire primary catalog needs an explicit
        ``all_files=True``, so an unfiltered call can never start a
        multi-terabyte transfer by mistake.
        """
        if files is not None:
            filters = (
                include,
                exclude,
                date,
                start,
                end,
                limit,
                sampling_rate,
                channel_spacing,
                gauge_length,
            )
            if any(value is not None for value in filters) or (
                buffer or all_files or all_file_types
            ):
                raise ValueError(
                    "files= is already an exact selection; drop the other "
                    "selection options"
                )
            selected = list(files)
        else:
            explicit = bool(
                _patterns(include)
                or date is not None
                or start is not None
                or end is not None
                or all_files
                or all_file_types
            )
            if not explicit:
                raise ValueError(_SELECTION_HINT)
            selected = self.list_files(
                include=include,
                exclude=exclude,
                date=date,
                start=start,
                end=end,
                buffer=buffer,
                limit=limit,
                all_file_types=all_file_types,
                sampling_rate=sampling_rate,
                channel_spacing=channel_spacing,
                gauge_length=gauge_length,
            )

        return download_dataset_files(
            self.client(for_download=True),
            self.spec,
            selected,
            self.name if out is None else out,
            overwrite=overwrite,
        )

    def __repr__(self) -> str:
        return (
            f"Dataset({self.name!r}, format={self.data_format!r}, "
            f"provider={self.provider!r})"
        )


def open_dataset(
    dataset: str | DatasetSpec | Dataset,
    *,
    client: DatasetClient | None = None,
    https_base_url: str | None = None,
) -> Dataset:
    """Return a :class:`Dataset` handle for a dataset id."""
    if isinstance(dataset, Dataset):
        return dataset
    spec = dataset if isinstance(dataset, DatasetSpec) else _spec(dataset)
    return Dataset(spec, client=client, https_base_url=https_base_url)


def list_datasets() -> list[str]:
    """Return every supported dataset id, e.g. for a `--help`-style listing."""
    return list(DATASETS)


def describe_datasets() -> list[dict]:
    """Return one row per dataset: id, name, summary, format, provider, and the
    one-line description of each acquisition configuration it recorded with."""
    return [
        {
            "id": spec.name,
            "name": spec.display_name,
            "summary": spec.summary,
            "format": spec.block_label,
            "provider": provider_type(spec),
            "configurations": [config.describe() for config in spec.configurations],
        }
        for spec in DATASETS.values()
    ]


def login(*, provider: str, no_browser: bool = False) -> Path:
    """Authorize daspull with a login-gated access provider.

    Only Globus needs this (``provider="globus"``) -- every other dataset
    here is served anonymously. *provider* has no default, mirroring the CLI's
    `daspull login --globus`: a second login-gated provider gets its own
    accepted value here rather than silently changing what a bare call does.
    """
    if provider not in _LOGIN_PROVIDERS:
        raise ValueError(
            f"Unsupported login provider: {provider!r}; supported: "
            + ", ".join(_LOGIN_PROVIDERS)
        )
    flow = start_native_login()
    print(f"DASPull Globus client: {GLOBUS_CLIENT_ID}")
    print(f"Open this URL to authorize DASPull:\n\n{flow.authorization_url}\n")
    if not no_browser:
        try:
            browser_opened = webbrowser.open(flow.authorization_url)
        except webbrowser.Error:
            browser_opened = False
        if not browser_opened:
            print(
                "No local browser was opened. Open the URL on another "
                "computer and paste the resulting code here."
            )

    value = input("Paste the authorization code (or redirect URL): ")
    response = exchange_authorization_code(flow, value)
    store = TokenStore()
    store.save_response(response)
    print(f"Login successful. Tokens saved locally in {store.path}")
    return store.path


def logout(*, provider: str) -> bool:
    """Remove locally stored credentials for *provider*.

    Returns whether any were stored. See :func:`login` for why *provider*
    has no default.
    """
    if provider not in _LOGIN_PROVIDERS:
        raise ValueError(
            f"Unsupported logout provider: {provider!r}; supported: "
            + ", ".join(_LOGIN_PROVIDERS)
        )
    return TokenStore().clear()


def list_files(
    dataset: str | DatasetSpec | Dataset,
    *,
    client: DatasetClient | None = None,
    **selection,
) -> list[RemoteFile]:
    """List one dataset's matching remote files. See :meth:`Dataset.list_files`."""
    return open_dataset(dataset, client=client).list_files(**selection)


def list_intervals(
    dataset: str | DatasetSpec | Dataset,
    *,
    client: DatasetClient | None = None,
    **selection,
) -> list[Interval]:
    """Return one dataset's coverage intervals. See :meth:`Dataset.list_intervals`."""
    return open_dataset(dataset, client=client).list_intervals(**selection)


def download(
    target: str | DatasetSpec | Dataset | Sequence[str],
    out: str | Path | None = None,
    *,
    client: DatasetClient | None = None,
    overwrite: bool = False,
    **selection,
) -> list[Path]:
    """Download from a dataset, or straight from one or more direct URLs.

    Mirrors the CLI's two shapes -- ``daspull <dataset> [options]`` and
    ``daspull <url>``::

        daspull.download("das4microseism", "data", date="2020-07-05")
        daspull.download("https://example.org/file.h5", "data")

    Returns the local paths written. See :meth:`Dataset.download` for the
    dataset selection keywords.
    """
    urls = _urls(target)
    if urls is not None:
        if selection:
            raise ValueError(
                "dataset selection options ("
                + ", ".join(sorted(selection))
                + ") cannot be combined with a direct URL"
            )
        if client is not None:
            raise ValueError("a direct URL download does not use a dataset client")
        return download_many(urls, "." if out is None else out, overwrite=overwrite)

    return open_dataset(target, client=client).download(
        out, overwrite=overwrite, **selection
    )


def download_url(
    url: str | Sequence[str],
    out: str | Path = ".",
    *,
    overwrite: bool = False,
) -> list[Path]:
    """Download one or more direct URLs, bypassing the dataset registry."""
    urls = _urls(url)
    if urls is None:
        raise ValueError(f"not an http(s) URL: {url!r}")
    return download_many(urls, out, overwrite=overwrite)


def _spec(name: str) -> DatasetSpec:
    try:
        return DATASETS[name]
    except (KeyError, TypeError):
        known = ", ".join(DATASETS)
        raise ValueError(
            f"Unknown dataset {name!r}; supported datasets are: {known}"
        ) from None


def _urls(target: object) -> list[str] | None:
    """Return *target* as a URL list, or ``None`` if it is not URLs at all."""
    if isinstance(target, str):
        return [target] if target.startswith(_URL_SCHEMES) else None
    if isinstance(target, (list, tuple)) and target:
        values = [str(item) for item in target]
        if all(value.startswith(_URL_SCHEMES) for value in values):
            return values
    return None


def _patterns(value: str | Sequence[str] | None) -> tuple[str, ...]:
    """Accept a single glob as well as a sequence of them."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)
