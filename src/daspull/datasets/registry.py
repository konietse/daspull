from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from ..catalog import RemoteFile
from .acquisition import (
    AcquisitionConfig,
    acquisition_configs,
    select_configs,
)
from .intervals import merge_intervals
from .layout import (
    BlockRule,
    DirectoryRule,
    Interval,
    block_rules,
    directory_rules,
    overlaps,
)

CONFIG_DIR = Path(__file__).parent.parent / "configs"


@dataclass(frozen=True)
class DatasetSpec:
    """One supported DAS dataset, loaded from ``configs/<name>.yaml``."""

    name: str
    display_name: str
    summary: str
    block_label: str
    dataset_root: str
    primary_root: str
    primary_pattern: str
    blocks: tuple[BlockRule, ...]
    directories: tuple[DirectoryRule, ...]
    configurations: tuple[AcquisitionConfig, ...]
    metadata: dict = field(repr=False)

    def block_interval(self, remote: RemoteFile) -> Interval | None:
        """Return the UTC interval a file's name encodes, else ``None``.

        Files whose names match none of the dataset's timestamp conventions
        (readmes, geometry tables, citations, companion seismometer
        recordings) have no interval and are never time-selected.
        """
        for rule in self.blocks:
            interval = rule.interval(remote.name, remote.size)
            if interval is not None:
                return interval
        return None

    def file_is_in_time_range(
        self,
        remote: RemoteFile,
        *,
        start: datetime,
        end: datetime,
    ) -> bool:
        """Return whether a file's recorded interval overlaps ``[start, end)``."""
        interval = self.block_interval(remote)
        return interval is not None and overlaps(interval, start, end)

    def directory_may_overlap_time_range(
        self,
        directory: str,
        *,
        start: datetime,
        end: datetime,
    ) -> bool:
        """Return whether *directory* can hold files in ``[start, end)``."""
        for rule in self.directories:
            interval = rule.interval(directory)
            if interval is not None:
                return overlaps(interval, start, end)
        return True

    def acquisition_configs(
        self,
        *,
        sampling_rate: float | None = None,
        channel_spacing: float | None = None,
        gauge_length: float | None = None,
    ) -> tuple[AcquisitionConfig, ...]:
        """Resolve requested acquisition settings to this dataset's configurations.

        Raises :class:`~daspull.datasets.acquisition.AcquisitionSelectionError`
        when this dataset recorded with several configurations and none was
        identified. Both front ends go through here, so neither can select
        files from a mixed-settings dataset without the caller saying which
        settings apply.
        """
        return select_configs(
            self.configurations,
            sampling_rate=sampling_rate,
            channel_spacing=channel_spacing,
            gauge_length=gauge_length,
            dataset=self.display_name,
        )

    def file_used_configurations(
        self,
        remote: RemoteFile,
        configs: Sequence[AcquisitionConfig],
    ) -> bool:
        """Return whether an acquisition selection should keep *remote*.

        A file whose name encodes no block interval is not a recording and so
        has no acquisition settings to select on. Geometry tables, readmes,
        and companion seismometer files stay selectable whichever settings the
        caller asked for, since they are usually needed to use the data at all.
        """
        if not configs or all(config.is_whole_dataset for config in configs):
            return True
        interval = self.block_interval(remote)
        if interval is None:
            return True
        return any(config.covers(remote.path, interval) for config in configs)

    def directory_may_hold_configurations(
        self,
        directory: str,
        configs: Sequence[AcquisitionConfig],
    ) -> bool:
        """Return whether *directory* can hold files of any of *configs*.

        Lets a scan skip the subtrees of settings the caller did not ask for,
        the same way ``directory_may_overlap_time_range`` skips dates.
        """
        if not configs:
            return True
        return any(config.may_hold_directory(directory) for config in configs)

    def continuous_intervals(
        self,
        files: Iterable[RemoteFile],
    ) -> list[Interval]:
        """Merge the dataset's recorded blocks into continuous UTC intervals."""
        blocks = [
            interval
            for remote in files
            if (interval := self.block_interval(remote)) is not None
            and interval[0] < interval[1]
        ]
        return merge_intervals(blocks)


def load_dataset(path: str | Path) -> DatasetSpec:
    with open(path, encoding="utf-8") as handle:
        metadata = yaml.safe_load(handle)
    layout = metadata["layout"]
    return DatasetSpec(
        name=metadata["id"],
        display_name=metadata["name"],
        summary=layout["summary"],
        block_label=metadata["data"]["format"],
        dataset_root=metadata["access"]["root_path"],
        primary_root=layout["primary_root"],
        primary_pattern=layout["primary_pattern"],
        blocks=block_rules(layout["blocks"]),
        directories=directory_rules(layout.get("directories", ())),
        configurations=acquisition_configs(metadata["acquisition"]),
        metadata=metadata,
    )


def load_datasets(config_dir: str | Path = CONFIG_DIR) -> dict[str, DatasetSpec]:
    datasets = [load_dataset(path) for path in sorted(Path(config_dir).glob("*.yaml"))]
    return {dataset.name: dataset for dataset in datasets}


DATASETS: dict[str, DatasetSpec] = load_datasets()
