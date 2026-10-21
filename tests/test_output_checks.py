"""Tests of the checks of the finished output (`menu_tools/_output.py`).

The output directories are made by hand: three pages and the files the
build copies into `assets/`.
"""

import unittest
from pathlib import Path

from tests import support  # noqa: F401  (prepares sys.path)
from menu_tools import _core, _output  # noqa: E402

ROOT = support.ROOT
TOKENS = ("heron-4tx9", "crane-7m2p", "Rk4vTz8QwM2nLp6XhB9cJs")
#: A directory of the site the build does not write (the invitations).
ALLOWED = "/invite"
#: The text of the pages; never part of a message.
SECRET_TEXT = "Rosalind sits next to Leopold"


def page(base: str, body: str = "") -> str:
    """A page that passes every check of the output under `base`."""
    assets = f"{base.rstrip('/')}/assets"
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>Dinner menu</title>\n"
        f'<link rel="icon" href="{assets}/favicon.svg" type="image/svg+xml">\n'
        f'<link rel="stylesheet" href="{assets}/app.css">\n'
        f'<script src="{assets}/app.js" defer></script>\n'
        "</head>\n"
        "<body>\n"
        f"<p>{SECRET_TEXT}</p>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


#: The line of `body` in a page of `page`.
BODY_LINE = page("/").splitlines().index("") + 1


class OutputChecksTest(support.TempDirTestCase):
    def make_output(self, base: str = "/", bodies: dict | None = None) -> Path:
        """A new output directory (each call its own)."""
        out = self.tmp / f"out-{len(list(self.tmp.iterdir()))}"
        for token in TOKENS:
            (out / token).mkdir(parents=True)
            text = page(base, (bodies or {}).get(token, ""))
            (out / token / "index.html").write_text(text, encoding="utf-8")
        _core.copy_assets(ROOT / "assets", out / "assets")
        palette = _core.load_palette(ROOT / "assets" / "app.css")
        (out / "assets" / "favicon.svg").write_bytes(_core.favicon_svg(palette))
        return out

    def problems(self, out: Path, base: str = "/", allow=(), pages=TOKENS) -> list[str]:
        try:
            _output.check_menu_output(out, pages, base_path=base, allow_paths=allow)
        except _core.OutputError as exc:
            for message in exc.errors:
                self.assertNotIn("Rosalind", message)
                for token in TOKENS:
                    self.assertNotIn(token.lower(), message.lower())
            return exc.errors
        return []

    def test_a_clean_output_passes(self):
        for base in ("/", "/menu"):
            with self.subTest(base=base):
                out = self.make_output(base)
                stats = _output.check_menu_output(out, TOKENS, base_path=base, allow_paths=())
                self.assertEqual(stats.files, 6)
                self.assertEqual(sorted(path.name for path in (out / "assets").iterdir()),
                                 ["app.css", "app.js", "favicon.svg"])

    def test_a_style_attribute_is_refused(self):
        bodies = {
            "html": '<p style="color: red">Hello</p>',
            "svg": '<svg class="scheme" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" style="fill: red"/></svg>',
            "upper case": '<P STYLE="color: red">Hello</P>',
            "no value": "<div style>Hello</div>",
        }
        for name, body in bodies.items():
            with self.subTest(case=name):
                out = self.make_output(bodies={TOKENS[1]: body})
                self.assertEqual(
                    self.problems(out),
                    [f"…/index.html line {BODY_LINE}: {_output.STYLE_PROBLEM}"],
                )

    def test_an_attribute_that_only_ends_in_style_passes(self):
        out = self.make_output(bodies={TOKENS[0]: '<p data-style="x" class="style">Hello</p>'})
        self.assertEqual(self.problems(out), [])

    def test_the_text_style_is_no_attribute(self):
        out = self.make_output(bodies={TOKENS[0]: "<p>style=&quot;x&quot; is not markup</p>"})
        self.assertEqual(self.problems(out), [])

    def test_the_same_problem_in_several_files_is_one_line(self):
        body = '<p>one</p>\n<p style="margin: 0">two</p>\n<p style="margin: 0">three</p>'
        out = self.make_output(bodies={token: body for token in TOKENS})
        self.assertEqual(
            self.problems(out),
            [f"3 files: {_output.STYLE_PROBLEM}; first: …/index.html line {BODY_LINE + 1}"],
        )

    def test_every_problem_comes_in_one_error(self):
        out = self.make_output(bodies={TOKENS[0]: '<p style="color: red">x</p>'})
        (out / "notes.txt").write_text("x", encoding="utf-8")
        self.assertEqual(
            self.problems(out),
            [
                "notes.txt: unexpected file at the top of the output (the build writes the pages "
                "and assets/ only)",
                f"…/index.html line {BODY_LINE}: {_output.STYLE_PROBLEM}",
            ],
        )

    def test_an_extra_file_or_a_missing_page(self):
        out = self.make_output()
        (out / TOKENS[0] / "notes.html").write_text(page("/"), encoding="utf-8")
        (out / "assets" / "extra.json").write_text("{}", encoding="utf-8")
        problems = self.problems(out, pages=TOKENS + ("wren-5tc3",))
        self.assertEqual(
            problems,
            [
                "assets/extra.json: '.json' files must not be published",
                "…/notes.html: unexpected file (only index.html is allowed in the directory of a page)",
                "…/index.html: missing from the output",
                f"assets/extra.json: unexpected file ({_output.ASSETS_RULE})",
            ],
        )

    def test_assets_hold_the_style_sheet_the_script_and_the_icon_alone(self):
        self.assertEqual(_output.ASSETS_RULE, "only app.css, app.js and favicon.svg are published in assets/")
        # files the invitations would publish in assets/: a note, a font, a picture
        out = self.make_output()
        (out / "assets" / "notes.txt").write_text("x", encoding="utf-8")
        (out / "assets" / "fonts").mkdir()
        (out / "assets" / "fonts" / "body.woff2").write_bytes(b"wOF2")
        (out / "assets" / "logo.png").write_bytes(b"\x89PNG")
        self.assertEqual(
            self.problems(out),
            [
                f"assets/fonts/: unexpected directory ({_output.ASSETS_RULE})",
                f"assets/logo.png: unexpected file ({_output.ASSETS_RULE})",
                f"assets/notes.txt: unexpected file ({_output.ASSETS_RULE})",
            ],
        )
        self.assertEqual(_output.asset_problems(self.make_output()), [])

    def test_a_link_under_an_allowed_path_passes(self):
        for base in ("/", "/menu"):
            with self.subTest(base=base):
                out = self.make_output(base, {TOKENS[0]: f'<a href="{ALLOWED}/{TOKENS[0]}/">Back</a>'})
                self.assertEqual(self.problems(out, base, (ALLOWED,)), [])

    def test_a_link_outside_the_output_without_an_allowed_path(self):
        expected = {"/menu": "points outside the output", "/": "does not exist in the output"}
        for base, words in expected.items():
            with self.subTest(base=base):
                out = self.make_output(base, {TOKENS[0]: f'<a href="{ALLOWED}/{TOKENS[0]}/">Back</a>'})
                problems = self.problems(out, base)
                self.assertEqual(len(problems), 1, problems)
                self.assertTrue(problems[0].startswith(f"…/index.html line {BODY_LINE}: <a href>"), problems)
                self.assertIn(words, problems[0])

    def test_a_resource_under_an_allowed_path_is_an_error(self):
        for base in ("/", "/menu"):
            with self.subTest(base=base):
                out = self.make_output(base, {TOKENS[2]: f'<img src="{ALLOWED}/x.png" alt="">'})
                problems = self.problems(out, base, (ALLOWED,))
                self.assertEqual(len(problems), 1, problems)
                self.assertTrue(problems[0].startswith(f"…/index.html line {BODY_LINE}: <img src>"), problems)

    def test_a_refused_allowed_path_raises_before_anything_is_read(self):
        missing = self.tmp / "missing"
        for base, allow in (("/", "/"), ("/menu", "/menu"), ("/menu", "/menu/x"), ("/invite/x", "/invite"),
                            ("/", "/assets"), ("/", f"/{TOKENS[0].upper()}")):
            with self.subTest(base=base, allow=allow):
                with self.assertRaises(ValueError) as caught:
                    _output.check_menu_output(missing, TOKENS, base_path=base, allow_paths=(allow,))
                self.assertNotIn(TOKENS[0].lower(), str(caught.exception).lower())

    def test_the_number_of_lines_is_limited(self):
        out = self.make_output(bodies={TOKENS[0]: '<p style="color: red">x</p>'})
        for number in range(30):
            (out / f"extra-{number:02}.txt").write_text("x", encoding="utf-8")
        problems = self.problems(out)
        limit = _core.MAX_REPORTED_PROBLEMS
        self.assertEqual(len(problems), limit + 1)
        self.assertEqual(problems[-1], "… and 6 more problem(s) in the output")

    def test_the_style_check_alone_on_a_document(self):
        document = '<p>a</p>\n<svg><g style="x"><rect STYLE="y"/></g></svg>\n<p data-style="z">b</p>'
        self.assertEqual(_output.style_lines(document), [2, 2])
        self.assertEqual(_output.shown_path("heron-4tx9/index.html"), "…/index.html")
        self.assertEqual(_output.shown_path("assets/app.css"), "assets/app.css")
        self.assertEqual(_output.shown_path("notes.txt"), "notes.txt")


if __name__ == "__main__":
    unittest.main()
