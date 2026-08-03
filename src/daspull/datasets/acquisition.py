"""Acquisition configurations -- the settings a dataset's files were recorded with.

Most datasets recorded with one set of settings, so a config's ``acquisition``
section carries single ``sampling_rate_hz`` / ``channel_spacing_m`` /
``gauge_length_m`` values and there is nothing to choose. A few changed
settings mid-deployment. A config lists every configuration it
recorded with, and daspull refuses to select any files from such a dataset
until the caller says which settings they mean.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from ..timerange import parse_utc_datetime
from .layout import Interval

#: Relative tolerance for matching a caller's value against a configuration's,
#: so a rounded ``5.1`` finds a ``5.1048 m`` configuration.
MATCH_TOLERANCE = 0.01

#: The settings a caller can select a configuration by, in report order:
#: field name, name used in messages, unit, and short name used in summaries.
SELECTABLE = (
    ("sampling_rate_hz", "sampling rate", "Hz", ""),
    ("channel_spacing_m", "channel spacing", "m", "spacing"),
    ("gauge_length_m", "gauge length", "m", "gauge"),
)


class AcquisitionSelectionError(ValueError):
    """Raised when a caller has not identified one acquisition configuration."""


@dataclass(frozen=True)
class AcquisitionConfig:
    """One set of acquisition settings, and which files recorded with them."""

    sampling_rate_hz: float | None = None
    channel_spacing_m: float | None = None
    gauge_length_m: float | None = None
    number_of_channels: int | None = None
    root: str | None = None
    start: datetime | None = None
    end: datetime | None = None

    @property
    def is_whole_dataset(self) -> bool:
        """Whether this configuration covers every file (nothing to filter)."""
        return self.root is None and self.start is None and self.end is None

    def covers(self, path: str, block: Interval | None) -> bool:
        """Return whether a block at *path* recording *block* used these settings."""
        if self.root is not None and not path.startswith(self.root):
            return False
        if self.start is None and self.end is None:
            return True
        if block is None:
            # Nothing places an untimestamped file inside a time span.
            return False
        began = block[0]
        if self.start is not None and began < self.start:
            return False
        return self.end is None or began < self.end

    def may_hold_directory(self, directory: str) -> bool:
        """Return whether *directory* can contain files of this configuration."""
        if self.root is None:
            return True
        return directory.startswith(self.root) or self.root.startswith(directory)

    def describe(self) -> str:
        """Return a one-line summary used in errors and help."""
        scope = self._scope()
        return self._settings() + (f"  [{scope}]" if scope else "")

    def _settings(self) -> str:
        """Return the settings portion of :meth:`describe`, without scope."""
        parts = [
            f"{_number(getattr(self, field))} {unit} {short}".strip()
            for field, _, unit, short in SELECTABLE
            if getattr(self, field) is not None
        ]
        if self.number_of_channels is not None:
            parts.append(f"{self.number_of_channels} channels")
        return ", ".join(parts)

    def _scope(self) -> str:
        scope = []
        if self.root is not None:
            # The last component identifies the subtree; the full path is one
            # `--include` away and would dominate the line.
            scope.append(self.root.rstrip("/").rsplit("/", 1)[-1] + "/")
        if self.start is not None or self.end is not None:
            start = f"{self.start:%Y-%m-%d}" if self.start else "..."
            end = f"{self.end:%Y-%m-%d}" if self.end else "..."
            scope.append(f"{start} to {end}")
        return ", ".join(scope)


def acquisition_configs(acquisition: dict) -> tuple[AcquisitionConfig, ...]:
    """Build a dataset's configuration list from its ``acquisition`` section."""
    declared = acquisition.get("configurations")
    if not declared:
        return (
            AcquisitionConfig(
                sampling_rate_hz=acquisition.get("sampling_rate_hz"),
                channel_spacing_m=acquisition.get("channel_spacing_m"),
                gauge_length_m=acquisition.get("gauge_length_m"),
                number_of_channels=acquisition.get("number_of_channels"),
            ),
        )
    return tuple(_config(entry) for entry in declared)


def select_configs(
    configs: Sequence[AcquisitionConfig],
    *,
    sampling_rate: float | None = None,
    channel_spacing: float | None = None,
    gauge_length: float | None = None,
    dataset: str = "this dataset",
) -> tuple[AcquisitionConfig, ...]:
    """Return the one distinct settings value a caller's request identifies."""
    requested = {
        "sampling_rate_hz": sampling_rate,
        "channel_spacing_m": channel_spacing,
        "gauge_length_m": gauge_length,
    }
    given = {field: value for field, value in requested.items() if value is not None}

    for field, value in given.items():
        if all(getattr(config, field) is None for config in configs):
            label = _label(field)
            raise AcquisitionSelectionError(
                f"{label} is not published for {dataset}, so it cannot be "
                f"selected by {label} ({_number(value)})"
            )

    matching = tuple(
        config
        for config in configs
        if all(
            _matches(getattr(config, field), value) for field, value in given.items()
        )
    )
    if not matching:
        wanted = ", ".join(
            f"{_label(field)} {_number(value)}" for field, value in given.items()
        )
        raise AcquisitionSelectionError(
            f"no {dataset} acquisition configuration has {wanted}; "
            f"the available one(s) are:\n" + describe_configs(configs)
        )

    distinct = distinct_settings_count(matching)
    if distinct > 1:
        if given:
            raise AcquisitionSelectionError(
                f"this {dataset} selection still spans {distinct} different "
                "acquisition configurations; add --sampling-rate, "
                "--channel-spacing, or --gauge to narrow it down to one:\n"
                + describe_configs(matching)
            )
        raise AcquisitionSelectionError(
            f"{dataset} recorded with {distinct} different acquisition "
            "configurations; say which one you mean with --sampling-rate, "
            "--channel-spacing, or --gauge:\n" + describe_configs(matching)
        )
    return matching


def distinct_settings_count(configs: Sequence[AcquisitionConfig]) -> int:
    """Return how many distinct settings values *configs* cover.

    Two configurations that differ only in root/time scope (Stanford-3's
    duplicate 100 Hz run) record with identical settings, so mixing them
    carries none of the mixed-geometry risk this module exists to guard
    against and must not be counted as more than one option -- otherwise a
    caller who has already fully specified their settings is told to
    "specify further" when there is nothing left to specify.
    """
    return len({config._settings() for config in configs})


def _config(entry: dict) -> AcquisitionConfig:
    return AcquisitionConfig(
        sampling_rate_hz=entry.get("sampling_rate_hz"),
        channel_spacing_m=entry.get("channel_spacing_m"),
        gauge_length_m=entry.get("gauge_length_m"),
        number_of_channels=entry.get("number_of_channels"),
        root=entry.get("root"),
        start=_moment(entry.get("start")),
        end=_moment(entry.get("end")),
    )


def _moment(value: str | None) -> datetime | None:
    return None if value is None else parse_utc_datetime(value, option="start")


def _matches(available: float | None, requested: float) -> bool:
    if available is None:
        return False
    return math.isclose(float(available), float(requested), rel_tol=MATCH_TOLERANCE)


def describe_configs(configs: Sequence[AcquisitionConfig]) -> str:
    """Return one line per distinct settings value, merging shared-settings scopes."""
    scopes_by_settings: dict[str, list[str]] = {}
    order: list[str] = []
    for config in configs:
        settings = config._settings()
        if settings not in scopes_by_settings:
            scopes_by_settings[settings] = []
            order.append(settings)
        scope = config._scope()
        if scope:
            scopes_by_settings[settings].append(scope)
    lines = []
    for settings in order:
        scopes = scopes_by_settings[settings]
        suffix = f"  [{', '.join(scopes)}]" if scopes else ""
        lines.append(f"  {settings}{suffix}")
    return "\n".join(lines)


def _label(field: str) -> str:
    for name, label, _, _short in SELECTABLE:
        if name == field:
            return label
    raise AssertionError(f"not a selectable setting: {field}")


def _number(value: float) -> str:
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return text or "0"
