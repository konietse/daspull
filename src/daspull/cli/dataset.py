"""The ``daspull <dataset>`` subcommand -- one parser for all eighteen datasets.

:func:`build_dataset_parser` and :func:`main_dataset` are parameterized over a
:class:`~daspull.datasets.DatasetSpec`, so no dataset has argparse or selection
logic of its own and adding one stays a config-only change.

What does live here is the flag vocabulary: which combinations of
``--date``/``--start``/``--buffer`` make sense, and which of them a given run
needs. Those checks stay in this module rather than in
:mod:`daspull.timerange` or :mod:`daspull.datasets.acquisition` so their
messages can name the flags the user actually typed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..client import DatasetClient
from ..datasets import (
    DatasetSpec,
    continuous_dataset_intervals,
    download_dataset_files,
    is_exact_selection,
    scan_dataset_files,
    stat_dataset_files,
)
from ..datasets.acquisition import AcquisitionSelectionError, describe_configs
from ..providers import build_client
from ..providers.globus_auth import GlobusAuthError
from ..timerange import names_an_instant, resolve_time_range
from .output import (
    print_file,
    print_file_list,
    print_file_summary,
    print_time_intervals,
    write_time_intervals_csv,
)


def build_dataset_parser(dataset: DatasetSpec) -> argparse.ArgumentParser:
    description = (
        f"Browse or download the {dataset.display_name} dataset ({dataset.summary})."
    )
    epilog = None
    if len(dataset.configurations) > 1:
        # Settings changed during this deployment, so every run has to name the
        # ones it wants; list them here rather than only in the error message.
        description += (
            f" Recorded with {len(dataset.configurations)} different acquisition "
            "configurations, so --sampling-rate, --channel-spacing, or "
            "--gauge is required."
        )
        epilog = "Acquisition configurations:\n" + describe_configs(
            dataset.configurations
        )
    parser = argparse.ArgumentParser(
        prog=f"daspull {dataset.name}",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help=(
            f"Destination directory (default: {dataset.name}). With "
            "--list-intervals, also writes the listed intervals to "
            f"<dir>/{dataset.name}_intervals.csv when given."
        ),
    )
    parser.add_argument(
        "--list", action="store_true", help="List matching remote files only."
    )
    parser.add_argument(
        "--list-intervals",
        action="store_true",
        help=f"List continuous {dataset.block_label} coverage intervals in UTC.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the files and total size without downloading.",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="GLOB",
        help="Include paths matching GLOB; may be repeated.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="Exclude paths matching GLOB; may be repeated.",
    )
    parser.add_argument(
        "--start",
        nargs=2,
        metavar=("DATE", "TIME"),
        help="UTC interval start, inclusive (YYYY-MM-DD HH:MM:SS).",
    )
    parser.add_argument(
        "--end",
        nargs=2,
        metavar=("DATE", "TIME"),
        help="UTC interval end, exclusive (YYYY-MM-DD HH:MM:SS).",
    )
    parser.add_argument(
        "--date",
        nargs="+",
        metavar="DATE",
        help=(
            "Select an entire UTC year, month, or day (YYYY[-MM[-DD]]), or "
            "an exact UTC moment 'YYYY-MM-DD HH:MM:SS' combined with "
            "--buffer."
        ),
    )
    parser.add_argument(
        "--buffer",
        type=_non_negative_int,
        default=0,
        metavar="SECONDS",
        help=(
            "With an exact --date moment, include files within SECONDS "
            "before and after it (default: 0)."
        ),
    )
    parser.add_argument(
        "--sampling-rate",
        type=_positive_float,
        metavar="HZ",
        help="Select files recorded at this sampling rate.",
    )
    parser.add_argument(
        "--channel-spacing",
        type=_positive_float,
        metavar="METRES",
        help="Select files recorded at this channel spacing.",
    )
    parser.add_argument(
        "--gauge",
        type=_positive_float,
        metavar="METRES",
        help="Select files recorded at this gauge length.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=f"Select the entire primary {dataset.block_label} dataset.",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        help="Limit the number of matching files.",
    )
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace complete local files."
    )
    parser.add_argument(
        "--https-base-url",
        default=None,
        help=argparse.SUPPRESS,
    )
    return parser


def _build_dataset_client(
    dataset: DatasetSpec,
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> DatasetClient:
    """Build *dataset*'s access client, reporting login problems as CLI errors.

    :func:`daspull.providers.build_client` is the one place that knows which
    provider client a dataset needs; this only decides that a catalog-only run
    (``--list``/``--list-intervals``/``--dry-run``) never needs a data-access
    token.
    """
    catalog_only = args.list or args.list_intervals or args.dry_run
    try:
        return build_client(
            dataset,
            catalog_only=catalog_only,
            https_base_url=args.https_base_url,
        )
    except GlobusAuthError as exc:
        parser.error(str(exc))


def main_dataset(argv: list[str], dataset: DatasetSpec) -> int:
    parser = build_dataset_parser(dataset)
    args = parser.parse_args(argv)
    if args.list_intervals and (args.list or args.dry_run):
        parser.error("--list-intervals cannot be combined with --list or --dry-run")
    if args.list_intervals and args.limit is not None:
        parser.error("--limit cannot be combined with --list-intervals")
    if args.date and (args.start is not None or args.end is not None):
        parser.error("--date cannot be combined with --start or --end")
    if not args.date and (args.start is None) != (args.end is None):
        parser.error("--start and --end must be used together")
    if args.date and len(args.date) > 2:
        parser.error(
            "--date takes a single YYYY[-MM[-DD]] value, or a date and a "
            "time for an exact moment"
        )
    # A date and a time may arrive as two words or as one quoted argument.
    date = " ".join(args.date) if args.date else None
    if args.buffer and not (date and names_an_instant(date)):
        parser.error("--buffer requires an exact --date 'YYYY-MM-DD HH:MM:SS' moment")

    try:
        range_start, range_end = resolve_time_range(
            date=date,
            start=" ".join(args.start) if args.start else None,
            end=" ".join(args.end) if args.end else None,
            buffer=args.buffer,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if not (
        args.list
        or args.list_intervals
        or args.dry_run
        or args.all
        or args.include
        or range_start is not None
    ):
        parser.error(
            "choose --list/--list-intervals/--dry-run, a --start/--end "
            "interval, at least one --include GLOB, or the explicit --all flag"
        )

    try:
        configurations = dataset.acquisition_configs(
            sampling_rate=args.sampling_rate,
            channel_spacing=args.channel_spacing,
            gauge_length=args.gauge,
        )
    except AcquisitionSelectionError as exc:
        parser.error(str(exc))

    client = _build_dataset_client(dataset, args, parser)
    try:
        if args.list_intervals:
            print(
                f"daspull: scanning {dataset.display_name} "
                f"{dataset.block_label} blocks to determine continuous UTC "
                "intervals...",
                file=sys.stderr,
                flush=True,
            )
            intervals = continuous_dataset_intervals(
                client,
                dataset,
                include=args.include,
                exclude=args.exclude,
                start=range_start,
                end=range_end,
                configurations=configurations,
            )
            print_time_intervals(intervals)
            if args.output_dir is not None:
                csv_path = Path(args.output_dir) / f"{dataset.name}_intervals.csv"
                write_time_intervals_csv(intervals, csv_path)
                print(f"Saved: {csv_path}")
            return 0

        output_listing = args.list or args.dry_run
        patterns = (
            args.include
            if args.include
            else ([] if args.list else [dataset.primary_pattern])
        )
        exact_selection = is_exact_selection(patterns)

        if exact_selection:
            selected = stat_dataset_files(
                client,
                dataset,
                patterns,
                exclude=args.exclude,
                start=range_start,
                end=range_end,
                limit=args.limit,
                configurations=configurations,
            )
        else:
            print(
                f"daspull: scanning the {dataset.display_name} catalog; "
                "matches are shown as they are found...",
                file=sys.stderr,
                flush=True,
            )
            root = (
                dataset.primary_root
                if not args.include and not args.list
                else dataset.dataset_root
            )
            selected = []
            for remote in scan_dataset_files(
                client,
                dataset,
                root=root,
                include=patterns,
                exclude=args.exclude,
                start=range_start,
                end=range_end,
                limit=args.limit,
                configurations=configurations,
            ):
                selected.append(remote)
                if output_listing:
                    print_file(remote)

        if output_listing and exact_selection:
            print_file_list(selected)
        elif output_listing:
            print_file_summary(selected)
        if output_listing:
            return 0
        if not selected:
            print(
                f"daspull: no {dataset.display_name} files matched the selection",
                file=sys.stderr,
            )
            return 1

        paths = download_dataset_files(
            client,
            dataset,
            selected,
            args.output_dir if args.output_dir is not None else dataset.name,
            overwrite=args.overwrite,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"daspull: error: {exc}", file=sys.stderr)
        return 1

    for path in paths:
        print(f"Saved: {path}")
    return 0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be at least 0")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed
