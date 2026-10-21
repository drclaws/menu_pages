"""Privacy of the page trees (`menu_tools._page`), standard library only.

A guest page shows the shared parts of the menu and its own record, nothing
else.  The differential test changes everything a guest must not see (the
other records, every `staff` key, the requirements and allergens, the
sections and widgets for the staff only, the dish for the staff only, the
names and dietary notes of the seats, which seats are taken and which are
reserved) and expects the very same tree of
every guest.  The string tests look for those values, and for every token
(the own one too), in the trees; the structure tests check the fields a guest
tree leaves empty and the code of the guest page for the keys it may not read.
"""

import ast
import inspect
import json
import re
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from menu_tools import _core, _page, _schema, _table  # noqa: E402  (imported after sys.path is prepared)
from tests import fixtures  # noqa: E402


def build(menu, guests) -> _page.Trees:
    report = _core.Report()
    _schema.check_data(menu, guests, report)
    if report.errors:
        raise AssertionError(report.errors)
    trees = _page.build_trees(menu, guests, report)
    if report.errors:
        raise AssertionError(report.errors)
    return trees


def dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def guest_trees(trees: _page.Trees) -> dict[int, dict]:
    return {page.number: page.tree for page in trees.guests}


# --------------------------------------------------------------------------
# What a guest must not see
# --------------------------------------------------------------------------


def staff_strings(value, under_staff: bool = False) -> set[str]:
    """Every string under a `staff` key."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found |= staff_strings(item, under_staff or key == "staff")
    elif isinstance(value, list):
        for item in value:
            found |= staff_strings(item, under_staff)
    elif isinstance(value, str) and under_staff:
        found.add(value)
    return found


def all_strings(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for item in value.values():
            found |= all_strings(item)
    elif isinstance(value, list):
        for item in value:
            found |= all_strings(item)
    elif isinstance(value, str):
        found.add(value)
    return found


def staff_only_parts(menu: dict) -> list:
    """The sections and widgets for the staff only."""
    parts = []
    for section in menu["sections"]:
        if section.get("audience") == "staff":
            parts.append(section)
            continue
        parts += [widget for widget in section.get("widgets", []) if widget.get("audience") == "staff"]
    return parts


#: The fields of a section or a widget that hold texts (the others hold ids
#: and choices, which a guest page may share).
TEXT_FIELDS = ("text", "title", "eyebrow", "note", "footnote")


def texts_of(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found |= {item} if key in TEXT_FIELDS and isinstance(item, str) else texts_of(item)
    elif isinstance(value, list):
        for item in value:
            found |= texts_of(item)
    return found


def forbidden(menu: dict, guests: list, number: int) -> set[str]:
    """The values the tree of record `number` must not hold."""
    found: set[str] = set()
    for position, record in enumerate(guests, start=1):
        if position != number:
            found |= {record.get("token", ""), record.get("name", "")}
            found |= texts_of(record.get("sections", {}))
        found |= {seat.get("name", "") for seat in record.get("seats", [])}
    found |= staff_strings(menu)
    for requirement in (menu.get("requirements") or {}).values():
        found |= {requirement["label"], requirement.get("tag", "")}
    for allergen in (menu.get("allergens") or {}).values():
        found.add(allergen["label"])
    for member in (menu.get("couple") or {}).get("members", []):
        found |= {member["name"], member.get("role", "")}
    for part in staff_only_parts(menu):
        found |= texts_of(part)
    # the dishes only the parts for the staff show
    guest_items = all_strings([
        [widget for widget in section.get("widgets", []) if widget.get("audience") != "staff"]
        for section in menu["sections"]
        if section.get("audience") != "staff"
    ])
    for dish_id, dish in (menu.get("dishes") or {}).items():
        in_sets = any(dish_id in item["courses"] for item in (menu.get("sets") or {}).values())
        if dish_id not in guest_items and not in_sets:
            found |= {dish["name"], dish.get("ingredients", "")}
    return {item for item in found if item.strip()}


def occurs(needle: str, haystack: str) -> bool:
    """`needle` as a whole word of `haystack` (not inside a longer word)."""
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])", haystack) is not None


# --------------------------------------------------------------------------
# The differential test
# --------------------------------------------------------------------------


def scramble(menu: dict, guests: list, keep: int) -> None:
    """Change everything the guest of record `keep` must not see; the data
    stays valid."""
    # every string under a `staff` key
    def rewrite(value, under_staff=False):
        if isinstance(value, dict):
            for key, item in value.items():
                if under_staff and isinstance(item, str):
                    value[key] = f"Changed {key} text"
                else:
                    rewrite(item, under_staff or key == "staff")
        elif isinstance(value, list):
            for position, item in enumerate(value):
                if under_staff and isinstance(item, str) and not re.fullmatch(r"[a-z][a-z0-9-]*", item):
                    value[position] = "changed tag"
                else:
                    rewrite(item, under_staff)

    rewrite(menu)
    for dish in (menu.get("dishes") or {}).values():
        staff = dish.setdefault("staff", {})
        if menu.get("allergens"):
            staff["allergens"] = list(menu["allergens"])[:1]
        staff["note"] = "Changed note of the dish"
        staff["tags"] = ["changed"]
    menu.setdefault("staff", {})["reminder"] = "Changed reminder\nof the staff"
    # the requirements and the allergens
    letters = iter("QRSTUWXYZ")
    for requirement in (menu.get("requirements") or {}).values():
        requirement["letter"] = next(letters)
        requirement["label"] = "changed label"
        requirement["tag"] = "changed tag"
        requirement.pop("avoids", None)
    for allergen in (menu.get("allergens") or {}).values():
        allergen["label"] = "changed allergen"
    # the couple: names, roles and dietary notes; their seats stay
    for member in (menu.get("couple") or {}).get("members", []):
        member["name"] = "Changed"
        member["role"] = "changed role"
        member.pop("requirements", None)
    # the parts for the staff only, and one more of them
    for part in staff_only_parts(menu):
        for widget in [part] + part.get("widgets", []):
            if widget.get("type") == "text":
                widget["text"] = "Changed text for the staff"
            if widget.get("type") == "dishes":
                widget["title"] = "Changed title"
    for section in menu["sections"]:
        if section.get("type") != "cover":
            section["widgets"].append({"type": "text", "audience": "staff", "text": "Added for the staff"})
            break
    menu["sections"].append({
        "id": "kitchen",
        "title": "Kitchen",
        "audience": "staff",
        "widgets": [{"type": "text", "text": "Added staff section"}],
    })
    for dish_id, dish in (menu.get("dishes") or {}).items():
        if dish_id == "melon":  # the dish for the staff only
            dish["name"] = "Changed dish"
            dish["ingredients"] = "Changed ingredients"
    # the other records: names, tokens, notes, switches; their seats change
    # hands among them
    others = [
        record for position, record in enumerate(guests, start=1)
        if position != keep and record.get("staff") is not True
    ]
    seats = [record["seats"] for record in others]
    for record, moved in zip(others, seats[1:] + seats[:1]):
        record["seats"] = moved
        record["name"] = f"Other{len(record['token'])}"
        record["token"] = record["token"][::-1] + "-x"
        record["sections"] = {"main": {"note": "A note of another guest"}}
    for record in guests:
        if record.get("staff") is True:
            record["token"] = "Changed-staff-token-0123456789"
    # the taken and the reserved seats: another record takes a free or a
    # reserved seat, and a seat still free (without a table, the next number)
    # becomes the reserved one
    taken = {seat["number"] for record in guests for seat in record.get("seats", [])}
    taken |= {member["seat"] for member in (menu.get("couple") or {}).get("members", [])}
    menu.pop("reservedSeats", None)
    if menu.get("table"):
        free = [number for number in range(1, len(_table.expand_seats(menu["table"])) + 1) if number not in taken]
    else:
        free = [max(taken) + 1, max(taken) + 2]
    if others and free:
        others[0]["seats"].append({"number": free.pop(0), "name": "Changed seat"})
    if free:
        menu["reservedSeats"] = [free[0]]
    # the names and dietary notes of every seat, the own ones included
    requirement_ids = list(menu.get("requirements") or {})
    for record in guests:
        for seat in record.get("seats", []):
            seat["name"] = "Changed seat"
            seat["requirements"] = requirement_ids[:1]


class DifferentialTest(unittest.TestCase):
    def test_a_guest_tree_is_the_same_whatever_a_guest_must_not_see(self):
        for name, make in fixtures.SETS.items():
            menu, guests = make()
            before = guest_trees(build(menu, guests))
            for number in before:
                with self.subTest(fixture=name, record=number):
                    changed_menu, changed_guests = make()
                    scramble(changed_menu, changed_guests, number)
                    after = guest_trees(build(changed_menu, changed_guests))
                    self.assertEqual(dump(after[number]), dump(before[number]))

    def test_the_changes_reach_the_staff_page(self):
        # the changes are real: the staff tree differs in every fixture
        for name, make in fixtures.SETS.items():
            with self.subTest(fixture=name):
                menu, guests = make()
                before = build(menu, guests).staff.tree
                scramble(menu, guests, 1)
                after = build(menu, guests).staff.tree
                self.assertNotEqual(dump(after), dump(before))


# --------------------------------------------------------------------------
# Strings and structure
# --------------------------------------------------------------------------


class StringsTest(unittest.TestCase):
    def test_a_guest_tree_holds_nothing_of_the_others_nor_of_the_staff(self):
        checked = 0
        for name, make in fixtures.SETS.items():
            menu, guests = make()
            trees = build(menu, guests)
            for page in trees.guests:
                text = dump(page.tree)
                # what the shared texts and the own record hold is allowed
                allowed = dump(_page.public_menu(menu)) + "\n" + guests[page.number - 1]["name"]
                for value in forbidden(menu, guests, page.number):
                    if occurs(value, allowed):
                        continue
                    checked += 1
                    with self.subTest(fixture=name, record=page.number):
                        self.assertFalse(occurs(value, text), "a value a guest must not see")
        self.assertGreater(checked, 500)

    def test_a_guest_tree_holds_no_token(self):
        # not even its own: the token names the directory of the page alone
        for name, make in fixtures.SETS.items():
            menu, guests = make()
            for page in build(menu, guests).guests:
                text = dump(page.tree).lower()
                for token in fixtures.tokens(guests):
                    with self.subTest(fixture=name, record=page.number, own=token == page.token):
                        self.assertNotIn(token.lower(), text)

    def test_the_staff_tree_has_every_name_and_no_token_nor_note(self):
        for name, make in fixtures.SETS.items():
            with self.subTest(fixture=name):
                menu, guests = make()
                text = dump(build(menu, guests).staff.tree)
                for token in fixtures.tokens(guests):
                    self.assertNotIn(token, text)
                for record in guests:
                    for override in (record.get("sections") or {}).values():
                        if override.get("note"):
                            self.assertNotIn(override["note"], text)
                for person in fixtures.names(guests, menu):
                    if person not in ("Peggy and Victor",):  # a record for two: its seats are named
                        self.assertIn(person, text)


class StructureTest(unittest.TestCase):
    def test_a_guest_tree_leaves_the_staff_fields_empty(self):
        for name, make in fixtures.SETS.items():
            for page in build(*make()).guests:
                with self.subTest(fixture=name, record=page.number):
                    tree = page.tree
                    self.assertFalse(tree["isStaff"])
                    self.assertEqual(tree["staff"], {"updated": "", "contact": "", "reminder": ""})
                    self.assertEqual(
                        tree["counters"], {"guests": 0, "notes": 0, "guestsText": "", "notesText": "", "tableLabel": ""}
                    )
                    for item in tree["sections"]:
                        for widget in item["widgets"]:
                            self.check_guest_widget(widget)

    def check_guest_widget(self, widget: dict) -> None:
        kind = widget["type"]
        if kind == "seating":
            self.assertEqual((widget["legend"], widget["rows"], widget["footnote"]), ([], [], ""))
            if widget["scheme"] is not None:
                self.assertEqual(widget["scheme"]["badges"], [])
                self.assertFalse(widget["scheme"]["hidden"])
                self.assertEqual({seat["mark"] for seat in widget["scheme"]["seats"]}, {"none"})
        dishes = widget["items"] if kind == "dishes" else []
        if kind == "sets":
            for item in widget["items"]:
                self.assertEqual(item["swapLines"], [])
                dishes += item["courses"]
        for dish in dishes:
            self.assertEqual(
                (dish["allergens"], dish["tags"], dish["noRestrictions"], dish["swapLines"], dish["note"]),
                ([], "", False, [], ""),
            )
        if kind == "drinks":
            self.assertEqual(widget["list"], [])

    def test_the_staff_tree_leaves_the_guest_fields_empty(self):
        for name, make in fixtures.SETS.items():
            with self.subTest(fixture=name):
                tree = build(*make()).staff.tree
                self.assertTrue(tree["isStaff"])
                for item in tree["sections"]:
                    self.assertEqual(item["note"], "")
                    for widget in item["widgets"]:
                        if widget["type"] == "seating":
                            self.assertEqual((widget["mySeats"], widget["seatLabel"], widget["whoLabel"]), ([], "", ""))
                            if widget["scheme"] is not None:
                                self.assertEqual(widget["scheme"]["labels"], [])
                                self.assertNotIn("you", {seat["kind"] for seat in widget["scheme"]["seats"]})
                        if widget["type"] == "drinks":
                            self.assertEqual(widget["groups"], [])

    def test_the_projections_hold_no_private_key(self):
        for name, make in fixtures.SETS.items():
            with self.subTest(fixture=name):
                menu, guests = make()
                public = _page.public_menu(menu)
                keys = set()

                def walk(value):
                    if isinstance(value, dict):
                        keys.update(value)
                        for item in value.values():
                            walk(item)
                    elif isinstance(value, list):
                        for item in value:
                            walk(item)

                walk(public)
                for record in guests:
                    if record.get("staff") is not True:
                        walk(_page.own_record(record))
                self.assertFalse(
                    keys & {"token", "staff", "requirements", "allergens", "members", "role", "audience", "tag",
                            "letter"}
                )
                # no name of a seat: the own record keeps only the name of the record
                for record in guests:
                    if record.get("staff") is True:
                        continue
                    text = dump(public) + dump({**_page.own_record(record), "name": ""})
                    for seat in record["seats"]:
                        if seat.get("name"):
                            self.assertFalse(occurs(seat["name"], text))

    def test_the_guest_page_code_reads_no_private_key(self):
        # the code that builds a guest page never reads these keys
        private = {"token", "staff", "requirements", "allergens", "members", "role", "audience", "tag", "letter"}
        allowed = {
            # `public_menu` leaves the parts for the staff only out by their audience
            ("public_menu", "audience"),
            ("_public_widget", "audience"),
            # the couple: only the seats of its members
            ("_couple", "members"),
        }
        for function in (_page.public_menu, _page._public_widget, _page._public_dish, _page._couple,
                         _page.own_record, _page._GuestPage):
            tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
            for node in ast.walk(tree):
                key = None
                if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                    key = node.slice.value
                elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                      and node.func.attr in ("get", "setdefault", "pop") and node.args
                      and isinstance(node.args[0], ast.Constant)):
                    key = node.args[0].value
                if key in private:
                    self.assertIn((function.__name__, key), allowed, f"{function.__name__} reads '{key}'")


if __name__ == "__main__":
    unittest.main()
