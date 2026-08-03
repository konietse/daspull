"""The ``daspull login`` and ``daspull logout`` subcommands.

Only Globus needs either -- every other provider daspull supports serves its
data anonymously -- which is why ``--globus`` is a required flag rather than a
default: a second login-gated provider would get its own flag instead of
silently changing what a bare ``daspull login`` does.

The actual OAuth flow and token-store access live in :func:`daspull.api.login`
and :func:`daspull.api.logout`, so a Python caller has exactly the same
capability as this CLI; this module only parses argv and turns an in-flight
login's exceptions into an exit code.
"""

from __future__ import annotations

import argparse
import sys

from ..api import login, logout
from ..providers.globus_auth import GlobusAuthError, TokenStore


def main_login(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="daspull login",
        description="Authorize DASPull with a dataset access provider.",
    )
    providers = parser.add_mutually_exclusive_group(required=True)
    providers.add_argument(
        "--globus",
        action="store_const",
        const="globus",
        dest="provider",
        help="Log in to Globus using OAuth and PKCE.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser automatically.",
    )
    args = parser.parse_args(argv)

    try:
        login(provider=args.provider, no_browser=args.no_browser)
    except (GlobusAuthError, EOFError, KeyboardInterrupt) as exc:
        print(f"daspull: login failed: {exc}", file=sys.stderr)
        return 1
    return 0


def main_logout(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="daspull logout",
        description="Remove locally stored credentials for a provider.",
    )
    providers = parser.add_mutually_exclusive_group(required=True)
    providers.add_argument(
        "--globus",
        action="store_const",
        const="globus",
        dest="provider",
        help="Remove locally stored Globus tokens.",
    )
    args = parser.parse_args(argv)

    if logout(provider=args.provider):
        print(f"Removed local Globus tokens from {TokenStore().path}")
    else:
        print("No local DASPull Globus tokens were stored.")
    return 0
