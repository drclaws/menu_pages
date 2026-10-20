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

## Status: under development

The commands are not implemented yet: `build` and `validate` only report so
and exit with code 2. The data format and the commands will be described here
when they are.

## What's where

```
build.py               command line entry point (the commands are not implemented yet)
tests/                 unit tests (unittest, standard library only)
  test_cli.py          the command line: exit codes and messages
  test_ci_workflow.py  static checks of the CI workflow
.github/workflows/     unit tests and repository hygiene on every push and pull request
LICENSE                the MIT license
```

## Tests

Python 3.10 or newer is required; there are no third-party packages.

```
python3 -m unittest
```

## License

MIT, see [LICENSE](LICENSE).
