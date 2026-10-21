"""Privacy of the finished pages, read file by file after a build.

* the token of a guest is in its own directory and on its own page alone, as
  many times as the page has links back to the invitation and only inside
  `href="<prefix>/<token>/"`; the staff page holds no token of a guest;
* the token of the staff page is in no file at all (only the name of its
  directory);
* `{token}` is left nowhere;
* the name of a record (and of each of its seats) is on its own page and on
  the staff page alone;
* the labels of the dietary notes and of the allergens are on the staff page
  alone.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from tests import fixtures, support

import build  # noqa: E402  (support prepares sys.path)
from menu_tools import _core  # noqa: E402


def data_sets() -> dict[str, tuple[dict, list]]:
    """Every data set the pages are built from, by name: the fixtures and
    the examples."""
    sets = {f"fixture {name}": make() for name, make in fixtures.SETS.items()}
    for directory in sorted((support.ROOT / "examples").iterdir()):
        sets[f"examples/{directory.name}"] = tuple(
            json.loads((directory / name).read_text(encoding="utf-8")) for name in ("menu.json", "guests.json")
        )
    return sets


def record_names(guests: list) -> dict[str, set[int]]:
    """Name -> the numbers of the records that hold it (the name of the record
    or of one of its seats)."""
    names: dict[str, set[int]] = {}
    for number, record in enumerate(guests, start=1):
        found = {record.get("name")} | {seat.get("name") for seat in record.get("seats", [])}
        for name in found - {None, ""}:
            names.setdefault(name, set()).add(number)
    return names


def labels(menu: dict) -> set[str]:
    """The labels and tags of the dietary notes and the labels of the allergens."""
    found = set()
    for requirement in (menu.get("requirements") or {}).values():
        found |= {requirement["label"], requirement.get("tag", "")}
    for allergen in (menu.get("allergens") or {}).values():
        found.add(allergen["label"])
    return found - {""}


def link_counts(data_dir: Path) -> dict[int, int]:
    """Record number -> the number of links back to the invitation on its page."""
    trees = build.load_data(data_dir, _core.Report()).trees
    return {
        page.number: sum(1 for section in page.tree["sections"] for widget in section["widgets"]
                         if widget["type"] == "link")
        for page in trees.guests
    }


def privacy_problems(out: Path, menu: dict, guests: list, links: dict[int, int]) -> list[str]:
    """What the finished output shows that it must not, as readable lines."""
    problems: list[str] = []
    files = {name: (out / name).read_text(encoding="utf-8") for name in support.tree_files(out)}
    numbers = {record["token"]: number for number, record in enumerate(guests, start=1)}
    staff = {record["token"] for record in guests if record.get("staff") is True}
    pages = {token: f"{token}/index.html" for token in numbers}
    staff_pages = {pages[token] for token in staff}
    href = (menu.get("invitationLink") or {}).get("href", "")
    for name, text in files.items():
        lowered = text.lower()
        if "{token}" in text:
            problems.append(f"{name}: '{{token}}' is left")
        for token, number in numbers.items():
            if token.lower() not in lowered:
                continue
            if token in staff:
                problems.append(f"{name}: the staff token")
            elif name != pages[token]:
                problems.append(f"{name}: the token of guest #{number}")
        for word, owners in record_names(guests).items():
            allowed = {pages[guests[owner - 1]["token"]] for owner in owners} | staff_pages
            if name not in allowed and support.occurs(word, text):
                problems.append(f"{name}: the name {word!r}")
        if name not in staff_pages:
            problems += [f"{name}: the label {word!r}" for word in sorted(labels(menu)) if support.occurs(word, text)]
    for token, number in numbers.items():
        if token in staff:
            continue
        text = files[pages[token]]
        expected = links.get(number, 0)
        found = text.lower().count(token.lower())
        own = text.lower().count(f'href="{href.replace("{token}", token)}"'.lower()) if href else 0
        if not found == own == expected:
            problems.append(
                f"{pages[token]}: the own token {found} time(s), in the link back {own} time(s), "
                f"{expected} link(s) back expected"
            )
    return problems


class OutputPrivacyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="menu-privacy-test-")
        cls.addClassCleanup(temporary.cleanup)
        cls.tmp = Path(temporary.name).resolve()
        cls.built = {}
        for index, (name, (menu, guests)) in enumerate(data_sets().items()):
            data = fixtures.write_data(cls.tmp / f"data-{index}", menu, guests)
            for base in ("/", "/menu"):
                out = cls.tmp / f"out-{index}{base.replace('/', '-')}"
                allowed = support.allowed_path(menu)
                allow = ["--allow-path", allowed] if allowed else []
                result = support.run_main("build", "--data", data, "--out", out, "--base-path", base, *allow)
                if result.returncode != 0:
                    raise AssertionError(result.stderr)
                cls.built[name, base] = (out, menu, guests, link_counts(data))

    def test_the_finished_pages_show_what_they_may(self):
        for (name, base), (out, menu, guests, links) in self.built.items():
            with self.subTest(data=name, base=base):
                self.assertEqual(privacy_problems(out, menu, guests, links), [])

    def test_the_pages_of_a_menu_with_a_link_back_have_it(self):
        for (name, base), (out, menu, guests, links) in self.built.items():
            with self.subTest(data=name, base=base):
                expected = 1 if menu.get("invitationLink") else 0
                self.assertEqual(set(links.values()), {expected})

    def test_the_names_are_not_part_of_the_shared_texts(self):
        # otherwise a name on a page would prove nothing
        for (name, _base), (out, menu, guests, _links) in self.built.items():
            with self.subTest(data=name):
                shared = json.dumps(menu, ensure_ascii=False)
                for word in record_names(guests):
                    self.assertFalse(support.occurs(word, shared), word)

    def test_the_check_finds_what_leaks(self):
        out, menu, guests, links = self.built["fixture reserved19", "/menu"]
        copy = self.tmp / "tampered"
        shutil.copytree(out, copy)
        self.addCleanup(shutil.rmtree, copy)
        first, second = guests[0], guests[1]
        staff = next(record["token"] for record in guests if record.get("staff") is True)
        page = copy / first["token"] / "index.html"
        text = page.read_text(encoding="utf-8")
        leak = f"<p>{second['name']} {staff} {first['token']}</p></main>"
        page.write_text(text.replace("</main>", leak, 1), encoding="utf-8")
        with open(copy / "assets" / "app.css", "a", encoding="utf-8") as handle:
            handle.write(f"/* {first['token'].upper()} no nuts */\n")
        problems = privacy_problems(copy, menu, guests, links)
        self.assertIn(f"{first['token']}/index.html: the name {second['name']!r}", problems)
        self.assertIn(f"{first['token']}/index.html: the staff token", problems)
        self.assertIn("assets/app.css: the token of guest #1", problems)
        self.assertIn("assets/app.css: the label 'no nuts'", problems)
        self.assertTrue(any(re.match(rf"{re.escape(first['token'])}/index\.html: the own token", line)
                            for line in problems), problems)


if __name__ == "__main__":
    unittest.main()
