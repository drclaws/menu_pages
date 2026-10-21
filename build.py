#!/usr/bin/env python3
"""Builder of personal dinner-menu pages.

    python build.py build
    python build.py validate

The builder writes a page per guest and a staff page for the restaurant, each
at a secret address `<base path>/<token>/`.  Only the Python 3 standard library
is used (Python >= 3.10).

The commands are not implemented yet: each of them reports so on stderr and
exits with code 2.  They take no parameters for now; the parameters come
together with the commands.

Importing this module has no side effects: everything happens inside `main()`.

Exit codes: 0 - success (`--help`), 1 - the invitations builder is missing in
`site/` (the submodule is not checked out), 2 - bad command line or a command
that is not implemented yet.
"""

import argparse
import sys
from pathlib import Path

#: The commands and their one-line descriptions.
COMMANDS = {
    "build": "build the pages of the guests and the staff page",
    "validate": "check the data without writing anything",
}


def make_parser() -> argparse.ArgumentParser:
    """The command line parser: a required subcommand (build or validate), no parameters yet."""
    parser = argparse.ArgumentParser(
        prog=Path(__file__).name,
        description="Builder of personal dinner-menu pages (not implemented yet).",
    )
    commands = parser.add_subparsers(dest="command", metavar="command", required=True)
    for name, summary in COMMANDS.items():
        commands.add_parser(name, help=summary, description=summary)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line; argparse exits by itself on `--help` and usage errors."""
    args = make_parser().parse_args(argv)
    try:
        from menu_tools import _core  # noqa: F401  (loads the invitations builder)
    except ImportError as exc:
        if exc.name != "invitations_build":  # not the bridge's own error
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"error: '{args.command}' is not implemented yet", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
