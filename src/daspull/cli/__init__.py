"""The ``daspull`` command line.

:func:`main` dispatches the three shapes an invocation can take:

* ``daspull login|logout --globus`` -- :mod:`daspull.cli.login`
* ``daspull <dataset> [options]`` -- :mod:`daspull.cli.dataset`, one subcommand
  per entry in :data:`daspull.datasets.DATASETS`, all built by the same
  parameterized parser so there is no per-dataset argparse to keep in sync
* ``daspull <url> ...`` -- the bare-URL fallback below, which needs no dataset
  at all

Argument parsing lives here and in those two modules, printing in
:mod:`daspull.cli.output`, and every actual capability in
:mod:`daspull.datasets`. Nothing in this package may hold selection, provider,
or time-parsing logic: :mod:`daspull.api` is its Python twin and has to be able
to do exactly the same things.
"""

from __future__ import annotations

import argparse
import sys

from ..datasets import DATASETS
from ..download import download_many
from .dataset import build_dataset_parser, main_dataset
from .login import main_login, main_logout

__all__ = ["build_dataset_parser", "build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    dataset_commands = ", ".join(f"`daspull {name} --help`" for name in DATASETS)
    parser = argparse.ArgumentParser(
        prog="daspull",
        description="Download DAS data without heavyweight tools like Globus.",
        epilog=(
            "Dataset commands: `daspull login --globus`, "
            f"`daspull logout --globus`, {dataset_commands}."
        ),
    )
    parser.add_argument("urls", nargs="+", help="One or more direct URLs to download.")
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Destination directory (default: current dir).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download even if the file already exists.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "login":
        return main_login(argv[1:])
    if argv and argv[0] == "logout":
        return main_logout(argv[1:])
    if argv and argv[0] in DATASETS:
        return main_dataset(argv[1:], DATASETS[argv[0]])

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        paths = download_many(args.urls, args.output_dir, overwrite=args.overwrite)
    except Exception as exc:  # noqa: BLE001
        print(f"daspull: error: {exc}", file=sys.stderr)
        return 1

    for p in paths:
        print(f"Saved: {p}")
    return 0
