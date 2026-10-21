"""Checks of the finished output of the menu builder.

The output is checked by the invitations' `check_output` without a media
directory: its allow-list then holds the layout of the menu, a directory
`<token>/` with `index.html` for every page and `assets/` with the files of
the code.  Every local address of a page, a link as well as a resource, has
to lie under the base path and name a file of the output: a page that leads
to another part of the site is an error.

On top of that, `assets/` holds `app.css`, `app.js` and `favicon.svg` and
nothing else (any other file of the code that would be published, a font or
a note, is a problem), and no element of a page may carry a `style`
attribute, inside an inline SVG as well: the styles of the pages live in
`assets/app.css` alone (the invitations' checks look at the URLs of a
`style` attribute, not at the attribute itself).

Every problem is reported in one `OutputError`, at most
`MAX_REPORTED_PROBLEMS` lines as in the invitations.  The messages never
quote the text of a page, and the directories of the pages are shown as `…`:
they are named after the tokens.
"""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

from menu_tools import _core

#: The directory of the files the pages share, at the top of the output.
ASSETS_DIR = "assets"
#: Everything `assets/` of the output holds.
ASSET_FILES = ("app.css", "app.js", "favicon.svg")

STYLE_PROBLEM = "the attribute 'style' is not allowed (the styles live in assets/app.css)"
ASSETS_RULE = f"only {', '.join(ASSET_FILES[:-1])} and {ASSET_FILES[-1]} are published in {ASSETS_DIR}/"

#: The last line of a list of problems that was cut short.
_MORE_RE = re.compile(r"… and (\d+) more problem\(s\) in the output\Z")


class _StyleFinder(HTMLParser):
    """Collects the lines of the elements with a `style` attribute."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.lines: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # the parser gives the names of the attributes in lower case
        if any(name == "style" for name, _value in attrs):
            self.lines.append(self.getpos()[0])


def style_lines(document: str) -> list[int]:
    """The lines of the elements of an HTML document that have a `style`
    attribute (of any element, the elements of an inline SVG included)."""
    finder = _StyleFinder()
    finder.feed(document)
    finder.close()
    return finder.lines


def shown_path(relative: str) -> str:
    """A path inside the output for a message: the directory of a page (any
    entry at the top but `assets` without a dot in its name) is `…`."""
    top, separator, rest = relative.partition("/")
    if top != ASSETS_DIR and "." not in top:
        top = _core.NAME_MASK
    return f"{top}{separator}{rest}"


def _html_files(root: Path) -> list[str]:
    """The HTML files below `root` as sorted relative '/' paths; symbolic
    links are never followed (`check_output` reports them)."""
    found: list[str] = []

    def walk(directory: Path, prefix: str) -> None:
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
        for entry in entries:
            relative = f"{prefix}{entry.name}"
            if entry.is_dir(follow_symlinks=False):
                walk(Path(entry.path), f"{relative}/")
            elif entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".html"):
                found.append(relative)

    walk(root, "")
    return found


def style_problems(out_dir: Path | str) -> list[str]:
    """The `style` attributes of the HTML files of an output directory, one
    line per file, or one line for every file at once:
    `3 files: <problem>; first: …/index.html line 12`."""
    root = Path(out_dir)
    places: list[tuple[str, int]] = []
    try:
        files = _html_files(root)
    except OSError as exc:
        raise _core.BuildError(
            f"cannot read the output directory {_core.display_path(root)}: {exc.strerror}"
        ) from None
    for relative in files:
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # `check_output` reports it
        except OSError as exc:
            raise _core.BuildError(f"cannot read {shown_path(relative)}: {exc.strerror}") from None
        lines = style_lines(text)
        if lines:
            places.append((shown_path(relative), lines[0]))
    if not places:
        return []
    first, line = places[0]
    if len(places) == 1:
        return [f"{first} line {line}: {STYLE_PROBLEM}"]
    return [f"{len(places)} files: {STYLE_PROBLEM}; first: {first} line {line}"]


def asset_problems(out_dir: Path | str) -> list[str]:
    """What `assets/` of an output directory holds besides `ASSET_FILES`,
    a line per entry at its top (a directory with a trailing '/').  The
    names are shown: they are the names of files of the code."""
    root = Path(out_dir) / ASSETS_DIR
    try:
        with os.scandir(root) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
    except FileNotFoundError:
        return []  # the pages refer to its files: `check_output` reports them missing
    except OSError as exc:
        raise _core.BuildError(f"cannot read {ASSETS_DIR}/ of the output: {exc.strerror}") from None
    problems: list[str] = []
    for entry in entries:
        if entry.name in ASSET_FILES and entry.is_file(follow_symlinks=False):
            continue
        if entry.is_dir(follow_symlinks=False):
            problems.append(f"{ASSETS_DIR}/{entry.name}/: unexpected directory ({ASSETS_RULE})")
        else:
            problems.append(f"{ASSETS_DIR}/{entry.name}: unexpected file ({ASSETS_RULE})")
    return problems


def _limited(problems: list[str], hidden: int) -> list[str]:
    """At most `MAX_REPORTED_PROBLEMS` lines and a count of the others."""
    limit = _core.MAX_REPORTED_PROBLEMS
    hidden += max(0, len(problems) - limit)
    problems = problems[:limit]
    if hidden:
        problems.append(f"… and {hidden} more problem(s) in the output")
    return problems


def check_menu_output(out_dir: Path | str, pages: Iterable[str], *, base_path: str) -> "_core.OutputStats":
    """Check a finished output directory of the menu published under
    `base_path`; `pages` are the tokens of every page (the guests and the
    staff).

    The invitations' `check_output` with no media directory, then the files
    of `assets/` and the `style` attributes of the pages; every problem
    together raises one `OutputError`.
    """
    problems: list[str] = []
    hidden = 0
    stats = None
    try:
        stats = _core.check_output(out_dir, list(pages), media_dir="", base_path=base_path)
    except _core.OutputError as exc:
        problems = list(exc.errors)
        more = _MORE_RE.match(problems[-1]) if problems else None
        if more:
            hidden = int(more.group(1))
            problems.pop()
    problems += asset_problems(out_dir)
    problems += style_problems(out_dir)
    if problems or stats is None:
        raise _core.OutputError(_limited(problems, hidden))
    return stats


__all__ = [
    "ASSET_FILES",
    "ASSETS_RULE",
    "STYLE_PROBLEM",
    "asset_problems",
    "check_menu_output",
    "shown_path",
    "style_lines",
    "style_problems",
]
