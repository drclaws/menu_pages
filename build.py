#!/usr/bin/env python3
"""Builder of personal dinner-menu pages.

    python build.py validate --data DIR
    python build.py build

The builder writes a page per guest and a staff page for the restaurant, each
at a secret address `<base path>/<token>/`.  Only the Python 3 standard library
is used (Python >= 3.10).

`validate` reads `menu.json` and `guests.json` in DIR (by default
`examples/data` next to this script), checks them, builds the page trees in
memory (that is how it learns what the pages show) and prints a summary.
Warnings and errors go to stderr; they never quote the data, and a token that
is part of a path in a message is hidden.  `build` is not implemented yet: it
reports so on stderr and exits with code 2.

Importing this module has no side effects: everything happens inside `main()`.

Exit codes: 0 - success (`--help`, valid data), 1 - errors in the data, or the
invitations builder is missing in `site/` (the submodule is not checked out),
2 - bad command line or a command that is not implemented yet.
"""

import argparse
import os
import sys
import traceback
from pathlib import Path
from typing import Any, NamedTuple

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

#: The directory of this script; the default data directory is relative to it.
CODE_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = Path("examples") / "data"

#: The commands and their one-line descriptions.
COMMANDS = {
    "build": "build the pages of the guests and the staff page",
    "validate": "check the data without writing anything",
}


def make_parser() -> argparse.ArgumentParser:
    """The command line parser: a required subcommand (build or validate)."""
    parser = argparse.ArgumentParser(
        prog=Path(__file__).name,
        description="Builder of personal dinner-menu pages.",
    )
    commands = parser.add_subparsers(dest="command", metavar="command", required=True)
    commands.add_parser("build", help=COMMANDS["build"], description=COMMANDS["build"])
    validate = commands.add_parser("validate", help=COMMANDS["validate"], description=COMMANDS["validate"])
    validate.add_argument(
        "--data",
        metavar="DIR",
        help=f"data directory with menu.json and guests.json (default: {DEFAULT_DATA_DIR} next to build.py)",
    )
    return parser


class Data(NamedTuple):
    """Checked data and the trees of its pages."""

    menu: dict
    guests: list
    #: What the checks learned (`menu_tools._schema.MenuIndex`).
    index: Any
    #: The page trees (`menu_tools._page.Trees`).
    trees: Any


def load_data(data_dir: Path | str, report: Any, settings: Any = None) -> Data:
    """Read and check `menu.json` and `guests.json` in `data_dir`, then build
    the page trees once.

    The order matters: `menu.json` first, because the keys of `guests.json`
    are shown in messages only when they are field names of the format or ids
    declared in `menu.json`; then the records; then the trees, which report a
    table plan that does not fit and tell what the pages show.  All errors
    are collected and raised together as a `ValidationError` (warnings go to
    the report as they come).
    """
    from menu_tools import _core, _page, _schema

    path = Path(data_dir)
    if not path.is_dir():
        report.error(f"data directory not found: {_core.display_path(path)}")
        report.raise_if_failed()
    menu = _core.read_json(path / _schema.MENU_FILE, report)
    index = _schema.check_menu(menu, report) if menu is not _core.MISSING else _schema.MenuIndex()
    guests = _core.read_json(path / _schema.GUESTS_FILE, report, _schema.guest_known(index))
    report.remember_tokens(guests)
    if guests is not _core.MISSING and index.version_ok:
        _schema.check_guests(guests, index, menu, report)
    report.raise_if_failed()
    trees = _page.build_trees(menu, guests, report, settings or _page.DEFAULT_SETTINGS)
    report.raise_if_failed()
    _schema.check_usage(index, menu, trees.usage, report)
    return Data(menu, guests, index, trees)


def summary(data: Data) -> str:
    """`validate: OK - 19 seat(s), 12 guest record(s) + staff, 8 dish(es), ...`"""
    index = data.index
    staff = " + staff" if data.trees.staff is not None else ""
    return (
        f"validate: OK - {index.seats} seat(s), {index.guests} guest record(s){staff}, "
        f"{len(index.dishes)} dish(es), {len(index.sets)} set(s), {len(index.drinks)} drink(s)"
    )


def _stdout(message: str) -> None:
    # Flushed on every line so that stdout and stderr stay in order in CI logs.
    print(message, flush=True)


def _stderr(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def cli_report() -> Any:
    """The report of a command: warnings go to stderr at once, with the
    tokens it has seen hidden (`Report.redact`)."""
    from menu_tools import _core

    def warn(message: str) -> None:
        _stderr(f"warning: {report.redact(message)}")

    report = _core.Report(on_warn=warn)
    return report


def cmd_validate(args: argparse.Namespace, report: Any) -> int:
    data_dir = Path(args.data) if args.data is not None else CODE_DIR / DEFAULT_DATA_DIR
    _stdout(summary(load_data(data_dir, report)))
    return EXIT_OK


def debug_enabled() -> bool:
    """`BUILD_DEBUG=1` (or `true` / `yes`) shows tracebacks of internal errors."""
    return os.environ.get("BUILD_DEBUG", "").strip().lower() in {"1", "true", "yes"}


def run_command(command: Any, args: argparse.Namespace) -> int:
    """Run a command; every message passes the report, which hides the tokens."""
    from menu_tools import _core

    report = cli_report()
    try:
        return int(command(args, report))
    except _core.ValidationError as exc:
        for message in exc.errors:
            _stderr(f"error: {report.redact(message)}")
        _stderr(f"{args.command}: failed with {len(exc.errors)} error(s)")
        return EXIT_ERROR
    except _core.BuildError as exc:
        _stderr(f"error: {report.redact(exc)}")
        _stderr(f"{args.command}: failed")
        return EXIT_ERROR
    except Exception as exc:  # unexpected: report without leaking data
        if debug_enabled():
            traceback.print_exc()
        else:
            # The message of the exception may quote the data, so only its
            # type and the place in the code are shown.
            frames = traceback.extract_tb(exc.__traceback__)
            where = f" at {os.path.basename(frames[-1].filename)}:{frames[-1].lineno}" if frames else ""
            _stderr(f"error: internal error: {type(exc).__name__}{where} (set BUILD_DEBUG=1 for the traceback)")
        _stderr(f"{args.command}: failed")
        return EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    """Run the command line; argparse exits by itself on `--help` and usage errors."""
    args = make_parser().parse_args(argv)
    try:
        from menu_tools import _core  # noqa: F401  (loads the invitations builder)
    except ImportError as exc:
        if exc.name != "invitations_build":  # not the bridge's own error
            raise
        _stderr(f"error: {exc}")
        return EXIT_ERROR
    if args.command == "validate":
        return run_command(cmd_validate, args)
    _stderr(f"error: '{args.command}' is not implemented yet")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
