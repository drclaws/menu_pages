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
  partials/section-nav.html   the line of the sections at the top of a page
  widgets/heading.html        the heading of a part of a section
assets/                the style sheet and the script of the pages
examples/data/         fictional data: an L-shaped table of 19 seats, dietary notes, a staff page
examples/data-plain/   fictional data without a table and dietary notes
site/                  submodule: the code of the invitations builder, pinned to a commit
tests/                 unit tests (unittest, standard library only)
.github/workflows/     unit tests, repository hygiene, builds of the examples and their checks
LICENSE                the MIT license
```

## Sections and navigation

`sections` of `menu.json` are the sections of a page in their order: the
cover (`"type": "cover"`, first) and sections of widgets. A widget is a text,
the seating, a list of dishes, the set switcher, the drinks or a heading.
`audience` (`all`, `guest` or `staff`) and `visible` choose the pages a
section or a widget is on; a guest record can switch them for its own page.

- `nav` of a section is the short label of its link in the line of the
  sections at the top of the page: one line of text, not empty. A section
  without it (the closing signature, say) has no link there, and a page links
  only the sections it shows. The cover has no label; two sections with the
  same label (letter case aside) get a warning.
- A widget of the type `heading` heads a part of its section: `title` (an
  h3), `eyebrow` in small capitals under it, and `staff: { title, eyebrow }`
  for the staff page. The widgets after it, up to the next heading, are its
  part; a set card in a part is an h4. A heading with nothing under it on a
  page is left out of that page, and `validate` warns about a heading at the
  end of a section or right before another one. `title` of a list of dishes
  stays a caption in small capitals, not a heading.

The line is a row of plain links to the sections of the page: nothing is
hidden, and without JavaScript a link jumps to its section. With it, the link
of the section in view is marked (`aria-current`), and a click keeps the mark
of its link while the page scrolls there. On the screen the line sticks to
the top, a section reached by a link stops under it, the scroll glides unless
the reader asks for less motion, and a line too long for the screen scrolls
sideways by itself; on a touch screen the body scrolls the page. Print leaves
the line out.

A page links only to its own parts: every `<a>` and `<area>` of the output has
an `href` of the form `#<id>`, the id of an element of the same page. The
build and CI refuse any other link, and no file of the output holds a token.

The food of `examples/data`, one section of two parts (a few fields left out):

```json
{
  "id": "food",
  "title": "Food",
  "nav": "Food",
  "widgets": [
    {
      "type": "heading",
      "title": "Starters",
      "eyebrow": "Shared plates for the table",
      "staff": { "eyebrow": "Shared plates · on the table by 19:15" }
    },
    { "type": "dishes", "items": ["bruschetta", "cheese-board", "hummus"] },
    { "type": "dishes", "audience": "staff", "title": "On request", "items": ["melon"] },
    {
      "type": "heading",
      "title": "Main course",
      "eyebrow": "Choose one of two sets",
      "staff": { "eyebrow": "Two sets · guests choose at the table" }
    },
    { "type": "sets", "items": ["fish", "meat"] },
    { "type": "text", "id": "allergy-card", "audience": "guest", "variant": "card", "text": "…" }
  ]
}
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
