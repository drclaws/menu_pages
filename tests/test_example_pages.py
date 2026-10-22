"""Tests of the example data sets and of the pages built from them."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from tests import support

from menu_tools import _schema  # noqa: E402  (support prepares sys.path)

ROOT = support.ROOT
EXAMPLES = ROOT / "examples"
#: name -> (data directory, arguments of the build)
SETS = {
    "data": (EXAMPLES / "data", ("--base-path", "/menu")),
    "data-plain": (EXAMPLES / "data-plain", ("--base-path", "/menu")),
}
#: Every address of a page: the shared files under the base path of the builds.
ASSETS_PREFIX = "/menu/assets/"
#: The attributes that hold an address.
ADDRESS_RE = re.compile(r'(?i)\b(?:href|src|srcset|poster|action|formaction)\s*=\s*"([^"]*)"')
SUMMARIES = {
    "data": "validate: OK - 19 seat(s), 12 guest record(s) + staff, 8 dish(es), 2 set(s), 5 drink(s)\n",
    "data-plain": "validate: OK - 4 seat(s), 3 guest record(s) + staff, 6 dish(es), 3 set(s), 2 drink(s)\n",
}


def load(directory: Path) -> tuple[dict, list]:
    return tuple(json.loads((directory / name).read_text(encoding="utf-8")) for name in ("menu.json", "guests.json"))


class ExampleDataTest(unittest.TestCase):
    def test_the_sets_are_the_directories_of_examples(self):
        self.assertEqual(sorted(path.name for path in EXAMPLES.iterdir()), sorted(SETS))
        for directory, _args in SETS.values():
            self.assertEqual(sorted(path.name for path in directory.iterdir()), ["guests.json", "menu.json"])

    def test_the_files_are_json_indented_by_two_with_a_final_newline(self):
        for directory, _args in SETS.values():
            for path in sorted(directory.iterdir()):
                with self.subTest(file=path.relative_to(ROOT).as_posix()):
                    text = path.read_bytes().decode("utf-8")
                    self.assertEqual(text, json.dumps(json.loads(text), ensure_ascii=False, indent=2) + "\n")

    def test_each_set_passes_validate_without_a_warning(self):
        for name, (directory, _args) in SETS.items():
            with self.subTest(set=name):
                result = support.run_main("validate", "--data", directory)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(result.stdout, SUMMARIES[name])

    def test_the_tokens(self):
        for name, (directory, _args) in SETS.items():
            with self.subTest(set=name):
                _menu, guests = load(directory)
                for record in guests:
                    if record.get("staff") is True:
                        self.assertRegex(record["token"], r"\A[A-Za-z0-9_-]{16,}\Z")
                    else:
                        self.assertRegex(record["token"], r"\A[a-z]+-[a-z0-9]{4}\Z")

    def test_the_names_of_the_people_are_not_part_of_the_shared_texts(self):
        for name, (directory, _args) in SETS.items():
            with self.subTest(set=name):
                menu, guests = load(directory)
                shared = json.dumps(menu, ensure_ascii=False)
                people = {record.get("name") for record in guests}
                people |= {seat.get("name") for record in guests for seat in record.get("seats", [])}
                for person in people - {None}:
                    self.assertFalse(support.occurs(person, shared), person)

    def test_the_main_set_shows_every_part_of_the_format(self):
        menu, guests = load(EXAMPLES / "data")
        widget_types = {widget["type"] for section in menu["sections"] for widget in section.get("widgets", [])}
        self.assertEqual(widget_types, set(_schema.WIDGET_TYPES))
        self.assertEqual(len(menu["reservedSeats"]), 1)
        sections = {section["id"]: section for section in menu["sections"]}
        self.assertEqual([tuple(item.get("audience", "all") for item in sections[name]["widgets"])
                          for name in ("food", "drinks")],
                         [("all", "all", "staff", "all", "all", "guest"), ("guest", "staff")])
        # the food in two parts under their headings, short texts under headings after the drinks
        self.assertEqual([item["type"] for item in sections["food"]["widgets"]],
                         ["heading", "dishes", "dishes", "heading", "sets", "text"])
        self.assertEqual([item["type"] for item in sections["info"]["widgets"]],
                         ["heading", "text", "heading", "text"])
        self.assertEqual([section["id"] for section in menu["sections"]],
                         ["cover", "seats", "food", "drinks", "info", "signature"])
        records = [record for record in guests if record.get("staff") is not True]
        seats = [record["seats"] for record in records]
        total = sum(1 for arm in menu["table"]["seats"] for _ in range(arm.get("count", 1)))
        # a guest on the last seat with a +1 on the first one
        self.assertIn([{"number": total}, {"number": 1, "plusOne": True, "name": "Hugo"}], seats)
        # a record for two, a +1 without a name, a seat with two dietary notes
        self.assertTrue(any(len(item) == 2 and "plusOne" not in item[1] for item in seats))
        self.assertTrue(any(item[-1] == {"number": item[-1]["number"], "plusOne": True} for item in seats))
        self.assertTrue(any(len(seat.get("requirements", [])) == 2 for item in seats for seat in item))
        self.assertEqual(sum(1 for record in records if "sections" in record), 2)


class ExamplePagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="menu-examples-test-")
        cls.addClassCleanup(temporary.cleanup)
        cls.tmp = Path(temporary.name).resolve()
        cls.built = {}
        for name, (directory, args) in SETS.items():
            out = cls.tmp / name
            result = support.run_main("build", "--data", directory, "--out", out, *args)
            if result.returncode != 0 or result.stderr:
                raise AssertionError(result.stderr)
            menu, guests = load(directory)
            pages = {record["token"]: (out / record["token"] / "index.html").read_text(encoding="utf-8")
                     for record in guests}
            staff = next(record["token"] for record in guests if record.get("staff") is True)
            cls.built[name] = (out, menu, guests, pages, staff)

    def test_the_output_holds_the_pages_and_three_assets(self):
        for name, (out, _menu, guests, _pages, _staff) in self.built.items():
            with self.subTest(set=name):
                expected = [f"{record['token']}/index.html" for record in guests]
                expected += ["assets/app.css", "assets/app.js", "assets/favicon.svg"]
                self.assertEqual(support.tree_files(out), sorted(expected))

    def test_the_pages_keep_away_from_search_engines_and_previews(self):
        for name, (_out, _menu, _guests, pages, _staff) in self.built.items():
            for token, page in pages.items():
                with self.subTest(set=name, page=token):
                    self.assertEqual(page.count('<meta name="robots" content="noindex, nofollow">'), 1)
                    self.assertNotRegex(page, r'(?i)<meta[^>]+(?:property|name)="og:')
                    self.assertIn('<link rel="stylesheet" href="/menu/assets/app.css">', page)

    def test_the_pages_link_nowhere(self):
        # no link at all, and every address is a shared file of the output
        for name, (_out, _menu, _guests, pages, _staff) in self.built.items():
            for token, page in pages.items():
                with self.subTest(set=name, page=token):
                    self.assertNotRegex(page, r"(?i)<a[\s/>]")
                    self.assertNotRegex(page, r"(?i)<area[\s/>]")
                    addresses = ADDRESS_RE.findall(page)
                    self.assertTrue(addresses)
                    for address in addresses:
                        self.assertTrue(address.startswith(ASSETS_PREFIX), address)

    def test_the_headings_have_no_gaps(self):
        # h1 the cover, h2 a section, h3 the heading of a part and a set
        # outside a part, h4 a set inside a part
        for name, (_out, _menu, _guests, pages, _staff) in self.built.items():
            for token, page in pages.items():
                levels = [int(level) for level in re.findall(r"<h([1-6])[\s>]", page)]
                with self.subTest(set=name, page=token):
                    self.assertEqual(levels.count(1), 1)
                    self.assertEqual(levels[0], 1)
                    for previous, level in zip(levels, levels[1:]):
                        self.assertLessEqual(level, previous + 1)

    def test_the_food_of_the_main_set_is_one_section_of_two_parts(self):
        _out, _menu, _guests, pages, _staff = self.built["data"]
        for token, page in pages.items():
            food = re.search(r'<section class="section" id="s-food".*?</section>', page, re.S).group(0)
            with self.subTest(page=token):
                self.assertEqual(re.findall(r"<h3 [^>]*>([^<]*)</h3>", food), ["Starters", "Main course"])
                self.assertEqual(re.findall(r'<h4 class="sets__title"[^>]*>([^<]*)</h4>', food), ["Set A", "Set B"])
                self.assertNotIn("<h3 class=\"sets__title\"", food)
                self.assertIn('aria-labelledby="s-food--w4--title"', food)
                info = re.search(r'<section class="section" id="s-info".*?</section>', page, re.S).group(0)
                self.assertEqual(re.findall(r"<h3 [^>]*>([^<]*)</h3>", info), ["Smoking", "Instant camera"])
        # the eyebrows of the staff page are its own
        staff = pages[self.built["data"][4]]
        self.assertIn("Shared plates · on the table by 19:15", staff)
        guest = pages[self.built["data"][2][0]["token"]]
        self.assertIn("Shared plates for the table", guest)
        self.assertNotIn("on the table by 19:15", guest)

    def test_the_table_plan_is_drawn_where_there_is_a_table(self):
        for name, (_out, menu, _guests, pages, staff) in self.built.items():
            for token, page in pages.items():
                with self.subTest(set=name, page=token):
                    expected = 1 if "table" in menu else 0
                    self.assertEqual(page.count('<svg class="scheme"'), expected)
                    if expected:
                        # the guest page names the drawing, the staff page hides it
                        self.assertEqual('role="img"' in page, token != staff)
        self.assertIn("table", self.built["data"][1])
        self.assertNotIn("table", self.built["data-plain"][1])

    def test_the_staff_bar_is_on_the_staff_page_alone(self):
        for name, (_out, _menu, _guests, pages, staff) in self.built.items():
            for token, page in pages.items():
                with self.subTest(set=name, page=token):
                    self.assertEqual("staff-bar" in page, token == staff)
                    self.assertEqual("Staff version · not for guests" in page, token == staff)
                    # the bar writes the word itself before the date of the data
                    self.assertEqual(bool(re.search(r">updated \d{1,2} [A-Z][a-z]+ \d{4}<", page)), token == staff)
                    self.assertNotIn("updated updated", page)
                    self.assertIn('<html lang="en" class="menu menu--staff">' if token == staff
                                  else '<html lang="en" class="menu menu--guest">', page)


if __name__ == "__main__":
    unittest.main()
