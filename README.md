# Personal dinner menus

A builder of static personal dinner-menu pages: one page per guest (their
seats, the menu, drinks) and one staff page for the restaurant, each at its own
secret address. It is the companion of a builder of personal invitations.

The principles behind all of the code:

- **static pages only** - no server, no database, no forms; the data is put
  into the HTML when the pages are built;
- **privacy by construction** - a guest's page holds nothing about other
  guests, and no page makes a single request to another domain;
- **progressive enhancement** - everything on a page is readable without
  JavaScript;
- **code and data kept apart** - this repository holds only code and fictional
  examples.

## Status

The builder works: it checks the data, builds the pages and checks the
finished output. The example data sets in `examples/` show every part of the
data format.

## What's where

```
build.py               command line entry point: build, validate, links, token
menu_tools/            the package of the builder
  _core.py             the bridge to the invitations builder in site/: all that is taken from it
  _schema.py           the checks of menu.json and guests.json
  _page.py             the page trees of the guests and of the staff
  _words.py            the words the build joins with numbers and names
  _table.py            the table plan: seat numbers, layout, the scheme
  _output.py           the checks of the finished output
template.html          the page template
fragments/             the fragments of the sections, the widgets and their parts
assets/                the style sheet and the script of the pages
examples/data/         fictional data: an L-shaped table of 19 seats, dietary notes, a staff page
examples/data-plain/   fictional data without a table and dietary notes
site/                  submodule: the code of the invitations builder, pinned to a commit
tests/                 unit tests (unittest, standard library only)
.github/workflows/     unit tests, repository hygiene, builds of the examples and their checks
LICENSE                the MIT license
```

## Commands

| Command | What it does |
|---|---|
| `python3 build.py build [--data DIR] [--out DIR] [--base-path PATH]` | checks the data, writes `<token>/index.html` for every guest record and for the staff record and `assets/` into `--out` (default: `dist`), which is replaced only when every check of the output has passed |
| `python3 build.py validate [--data DIR]` | checks the data and prints a summary; writes nothing |
| `python3 build.py links --url URL [--data DIR]` | prints the name of every guest record and the address of its page, `URL/<token>/`, the staff page last; the lines hold personal data, so the command is for local use only and refuses to run in CI |
| `python3 build.py token [--prefix NAME]` | prints a new token: fully random (for the staff record) or readable, `NAME-xxxx` |

`--data` is a directory with `menu.json` and `guests.json` (default:
`examples/data` next to `build.py`). `--base-path` is the path from the root of
the site under which the output is published (default: `/`).

Exit codes: `0` - success; `1` - errors in the data or in the finished output,
an `--out` that is not replaced, `links` in CI, or the submodule `site/` is not
checked out; `2` - a bad command line.

## Tests

Python 3.10 or newer is required; there are no third-party packages. The
code of the invitations builder comes with the submodule:

```
git submodule update --init --recursive
python3 -m unittest discover -s tests -t .
```

## License

MIT, see [LICENSE](LICENSE).
