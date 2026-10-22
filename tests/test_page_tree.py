"""Tests of the page trees (`menu_tools._page`) and their words (`menu_tools._words`).

The trees are built from the fictional fixtures; `ContractTest` holds the
fields of every node, the contract between the trees and the fragments.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from menu_tools import _core, _page, _schema, _words  # noqa: E402  (imported after sys.path is prepared)
from tests import fixtures  # noqa: E402

DASH = " — "
DOT = " · "


def build(menu, guests, settings=_page.DEFAULT_SETTINGS) -> tuple[_page.Trees, _core.Report]:
    """The trees of data that passes the checks."""
    report = _core.Report()
    index = _schema.check_data(menu, guests, report)
    if report.errors:
        raise AssertionError(report.errors)
    trees = _page.build_trees(menu, guests, report, settings)
    _schema.check_usage(index, menu, trees.usage, report)
    return trees, report


def guest_tree(trees: _page.Trees, guests: list, name: str) -> dict:
    number = next(n for n, item in enumerate(guests, 1) if item.get("name") == name)
    return next(page.tree for page in trees.guests if page.number == number)


def section(tree: dict, section_id: str) -> dict | None:
    return next((item for item in tree["sections"] if item["id"] == section_id), None)


def widgets(tree: dict, kind: str) -> list[dict]:
    return [widget for item in tree["sections"] for widget in item["widgets"] if widget["type"] == kind]


def seating(tree: dict) -> dict:
    (found,) = widgets(tree, "seating")
    return found


def centre(scheme: dict, number: int) -> tuple[float, float]:
    seat = next(item for item in scheme["seats"] if item["number"] == str(number))
    return float(seat["cx"]), float(seat["cy"])


def distance2(label: dict, point: tuple[float, float]) -> float:
    return (float(label["x"]) - point[0]) ** 2 + (float(label["y"]) - point[1]) ** 2


def reserved19_trees():
    menu, guests = fixtures.reserved19()
    trees, _report = build(menu, guests)
    return trees, menu, guests


# --------------------------------------------------------------------------
# Words
# --------------------------------------------------------------------------


class WordsTest(unittest.TestCase):
    def test_seat_label(self):
        self.assertEqual(_words.seat_label([8]), "Seat 8")
        self.assertEqual(_words.seat_label([9, 8]), "Seats 8 & 9")
        self.assertEqual(_words.seat_label([10, 8, 9]), "Seats 8, 9 & 10")
        self.assertEqual(_words.seat_label([19, 1]), "Seats 1 & 19")

    def test_mine_text(self):
        self.assertEqual(_words.mine_text([8]), "8")
        self.assertEqual(_words.mine_text([8, 9]), "8 and 9")
        self.assertEqual(_words.mine_text([19, 1]), "1 and 19")
        self.assertEqual(_words.mine_text([10, 8, 9]), "8, 9 and 10")

    def test_who_label(self):
        self.assertEqual(_words.who_label("Olga", []), "Olga")
        # the companions without a name
        self.assertEqual(_words.who_label("Olga", [""]), "Olga and your guest")
        self.assertEqual(_words.who_label("Olga", ["", ""]), "Olga and your guests")
        # the companions with a name, in their order
        self.assertEqual(_words.who_label("Olga", ["Oscar"]), "Olga and Oscar")
        self.assertEqual(_words.who_label("Olga", ["Oscar", "Hugo"]), "Olga, Oscar and Hugo")
        # both: the names first
        self.assertEqual(_words.who_label("Olga", ["Oscar", ""]), "Olga, Oscar and your guest")
        self.assertEqual(_words.who_label("Olga", ["", "Oscar"]), "Olga, Oscar and your guest")
        self.assertEqual(_words.who_label("Olga", ["", "Oscar", ""]), "Olga, Oscar and your guests")
        self.assertEqual(_words.who_label("Olga", ["Oscar", "", "Hugo"]), "Olga, Oscar, Hugo and your guest")

    def test_counters(self):
        self.assertEqual(_words.guests_text(1), "1 guest")
        self.assertEqual(_words.guests_text(14), "14 guests")
        self.assertEqual(_words.notes_text(0), "")
        self.assertEqual(_words.notes_text(1), "1 dietary note")
        self.assertEqual(_words.notes_text(5), "5 dietary notes")

    def test_swap_lines(self):
        self.assertEqual(_words.dish_swap_line([3], "serve it plain"), f"Seat 3{DASH}serve it plain")
        self.assertEqual(_words.dish_swap_line([14, 10], "no cheese"), f"Seats 10 & 14{DASH}no cheese")
        self.assertEqual(
            _words.set_swap_line([3], "no nuts", "serve it without the crust", first=True),
            f"If chosen by seat 3 (no nuts){DASH}serve it without the crust.",
        )
        self.assertEqual(
            _words.set_swap_line([10, 14], "no lactose", "serve it plain.", first=False),
            f"By seats 10 & 14 (no lactose){DASH}serve it plain.",
        )
        self.assertEqual(_words.drink_reminder([1], "no alcohol"), f"seat 1{DASH}no alcohol")
        self.assertEqual(_words.joined(["a", "", "b"]), f"a{DOT}b")


# --------------------------------------------------------------------------
# The seats of a guest
# --------------------------------------------------------------------------


class GuestSeatsTest(unittest.TestCase):
    def setUp(self):
        self.trees, self.menu, self.guests = reserved19_trees()

    def seating_of(self, name: str) -> dict:
        return seating(guest_tree(self.trees, self.guests, name))

    def test_one_seat(self):
        widget = self.seating_of("Boris")
        self.assertEqual(widget["seatLabel"], "Seat 4")
        self.assertEqual(widget["whoLabel"], "Boris")
        self.assertEqual(widget["mySeats"], [{"number": 4, "mark": "you"}])
        scheme = widget["scheme"]
        self.assertEqual(scheme["mine"], "4")
        self.assertTrue(scheme["single"])
        self.assertEqual([(lab["isYou"], lab["isPlusOne"]) for lab in scheme["labels"]], [(True, False)])

    def test_a_plus_one_without_a_name(self):
        widget = self.seating_of("Olga")
        self.assertEqual(widget["seatLabel"], "Seats 8 & 9")
        self.assertEqual(widget["whoLabel"], "Olga and your guest")
        self.assertEqual(widget["mySeats"], [{"number": 8, "mark": "you"}, {"number": 9, "mark": "plusOne"}])
        self.assertEqual(widget["scheme"]["mine"], "8 and 9")

    def test_a_plus_one_with_a_name(self):
        # the label under the plan names the companion; the marks on the plan are "You" and "+1"
        widget = self.seating_of("Nina")
        self.assertEqual(widget["seatLabel"], "Seats 15 & 16")
        self.assertEqual(widget["whoLabel"], "Nina and Oscar")
        self.assertEqual(widget["mySeats"], [{"number": 15, "mark": "you"}, {"number": 16, "mark": "plusOne"}])
        self.assertEqual([(lab["isYou"], lab["isPlusOne"]) for lab in widget["scheme"]["labels"]],
                         [(True, False), (False, True)])

    def test_a_plus_one_across_the_end_of_the_numbers(self):
        # the guest on seat 19, the +1 on seat 1: neighbours on the plan
        widget = self.seating_of("Greta")
        self.assertEqual(widget["seatLabel"], "Seats 1 & 19")
        self.assertEqual(widget["whoLabel"], "Greta and Hugo")
        self.assertEqual(widget["mySeats"], [{"number": 1, "mark": "plusOne"}, {"number": 19, "mark": "you"}])
        scheme = widget["scheme"]
        self.assertEqual(scheme["mine"], "1 and 19")
        self.assertFalse(scheme["single"])
        kinds = {seat["number"]: seat["kind"] for seat in scheme["seats"]}
        self.assertEqual((kinds["1"], kinds["19"]), ("you", "you"))
        you, plus_one = scheme["labels"]
        self.assertEqual((you["isYou"], you["isPlusOne"]), (True, False))
        self.assertEqual((plus_one["isYou"], plus_one["isPlusOne"]), (False, True))
        # "You" next to seat 19, "+1" next to seat 1
        self.assertLess(distance2(you, centre(scheme, 19)), distance2(you, centre(scheme, 1)))
        self.assertLess(distance2(plus_one, centre(scheme, 1)), distance2(plus_one, centre(scheme, 19)))
        self.assertEqual((you["x"], you["y"], plus_one["x"], plus_one["y"]), ("59", "142", "17", "38"))

    def test_a_record_for_two(self):
        widget = self.seating_of("Peggy and Victor")
        self.assertEqual(widget["seatLabel"], "Seats 2 & 3")
        self.assertEqual(widget["whoLabel"], "Peggy and Victor")
        self.assertEqual(widget["mySeats"], [{"number": 2, "mark": "you"}, {"number": 3, "mark": "none"}])
        scheme = widget["scheme"]
        kinds = {seat["number"]: seat["kind"] for seat in scheme["seats"]}
        self.assertEqual((kinds["2"], kinds["3"]), ("you", "you"))
        self.assertEqual([(lab["isYou"], lab["isPlusOne"]) for lab in scheme["labels"]], [(True, False)])

    def test_more_than_two_seats_get_no_marks(self):
        menu, guests = fixtures.mockup16()
        olga = guests[0]
        olga["seats"] += [{"number": 12, "plusOne": True}, {"number": 13, "name": "Ada"}]
        trees, _report = build(menu, guests)
        widget = seating(guest_tree(trees, guests, "Olga"))
        self.assertEqual(widget["seatLabel"], "Seats 8, 9, 12 & 13")
        self.assertEqual(widget["whoLabel"], "Olga and your guests")
        self.assertEqual({item["mark"] for item in widget["mySeats"]}, {"none"})
        self.assertEqual(widget["scheme"]["labels"], [])
        self.assertEqual(widget["scheme"]["mine"], "8, 9, 12 and 13")

    def test_companions_with_and_without_a_name(self):
        menu, guests = fixtures.mockup16()
        olga = guests[0]
        olga["seats"].append({"number": 12, "plusOne": True, "name": "Hugo"})
        trees, _report = build(menu, guests)
        self.assertEqual(seating(guest_tree(trees, guests, "Olga"))["whoLabel"], "Olga, Hugo and your guest")
        olga["seats"][1]["name"] = "Ada"
        trees, _report = build(menu, guests)
        self.assertEqual(seating(guest_tree(trees, guests, "Olga"))["whoLabel"], "Olga, Ada and Hugo")
        # a name of blanks is no name
        olga["seats"][2]["name"] = "  "
        trees, _report = build(menu, guests)
        self.assertEqual(seating(guest_tree(trees, guests, "Olga"))["whoLabel"], "Olga, Ada and your guest")

    def test_the_couple_on_the_plan_of_a_guest(self):
        scheme = self.seating_of("Boris")["scheme"]
        self.assertEqual(scheme["couple"]["text"], "IVAN · VERA")
        kinds = {seat["number"]: seat["kind"] for seat in scheme["seats"]}
        self.assertEqual((kinds["6"], kinds["7"]), ("couple", "couple"))
        self.assertEqual(scheme["badges"], [])
        self.assertEqual({seat["mark"] for seat in scheme["seats"]}, {"none"})
        self.assertFalse(scheme["hidden"])
        # the reserved seat is an ordinary seat on the plan
        self.assertEqual(kinds["13"], "regular")


# --------------------------------------------------------------------------
# The rest of a guest page
# --------------------------------------------------------------------------


class GuestPageTest(unittest.TestCase):
    def setUp(self):
        self.trees, self.menu, self.guests = reserved19_trees()

    def tree(self, name: str) -> dict:
        return guest_tree(self.trees, self.guests, name)

    def test_sections_and_widgets_of_a_guest(self):
        tree = self.tree("Boris")
        self.assertEqual(
            [(item["id"], [widget["type"] for widget in item["widgets"]]) for item in tree["sections"]],
            [
                ("cover", []),
                ("seats", ["seating"]),
                ("starters", ["dishes"]),
                ("main", ["sets", "text"]),
                ("drinks", ["drinks"]),
                ("signature", ["text"]),
            ],
        )
        (signature,) = section(tree, "signature")["widgets"]
        self.assertEqual((signature["text"], signature["variant"]), (fixtures.COUPLE_NAMES, "signature"))

    def test_the_token_names_the_page_and_is_not_in_its_tree(self):
        for name, make in fixtures.SETS.items():
            menu, guests = make()
            trees, _report = build(menu, guests)
            for page in trees.guests:
                with self.subTest(fixture=name, record=page.number):
                    self.assertEqual(page.token, guests[page.number - 1]["token"])
                    self.assertNotIn(page.token.lower(), json.dumps(page.tree).lower())

    def test_dom_ids_count_every_widget_of_the_data(self):
        boris = self.tree("Boris")
        gleb = self.tree("Gleb")
        self.assertEqual([w["domId"] for w in section(boris, "main")["widgets"]], ["s-main--w1", "s-main--w2"])
        # the hidden widget keeps its number
        self.assertEqual([w["domId"] for w in section(gleb, "main")["widgets"]], ["s-main--w1"])
        starters = section(boris, "starters")
        self.assertEqual((starters["domId"], starters["titleId"]), ("s-starters", "s-starters--title"))
        self.assertEqual(starters["widgets"][0]["labelledBy"], "s-starters--title")
        staff_starters = section(self.trees.staff.tree, "starters")
        self.assertEqual([w["domId"] for w in staff_starters["widgets"]], ["s-starters--w1", "s-starters--w2"])
        self.assertEqual([w["domId"] for w in section(self.trees.staff.tree, "drinks")["widgets"]], ["s-drinks--w2"])

    def test_a_note_to_a_section(self):
        self.assertEqual(
            section(self.tree("Timur"), "signature")["note"], "Thank you for coming all the way from the coast!"
        )
        self.assertEqual(section(self.tree("Boris"), "signature")["note"], "")

    def test_titles_and_eyebrows(self):
        self.assertEqual(section(self.tree("Boris"), "seats")["title"], "Your seat")
        self.assertEqual(section(self.tree("Olga"), "seats")["title"], "Your seats")
        starters = section(self.tree("Boris"), "starters")
        self.assertEqual((starters["title"], starters["eyebrow"]), ("Starters", "Shared plates for the table"))
        self.assertEqual(section(self.tree("Boris"), "drinks")["eyebrow"], "")

    def test_dishes_and_sets_of_a_guest(self):
        tree = self.tree("Boris")
        (dishes,) = widgets(tree, "dishes")
        self.assertEqual(dishes["title"], "")
        self.assertEqual([item["name"] for item in dishes["items"]], ["Tomato bruschetta", "Cheese board", "Hummus with vegetables"])
        self.assertEqual(dishes["items"][1]["ingredients"], "Three cheeses, honey, walnuts")
        (sets,) = widgets(tree, "sets")
        self.assertEqual((sets["count"], sets["multiple"]), (2, True))
        self.assertEqual(sets["note"], "Your waiter will take your choice after the starters.")
        fish = sets["items"][0]
        self.assertEqual((fish["id"], fish["domId"], fish["title"], fish["hint"]), ("fish", "s-main--w1--set-fish", "Set A", "Fish"))
        self.assertEqual((fish["eyebrow"], fish["pairing"], fish["swapLines"]), ("two courses", "white wine", []))
        self.assertEqual([course["name"] for course in fish["courses"]], ["Cured salmon", "Baked cod with an almond crust"])

    def test_drinks_of_a_guest(self):
        (drinks,) = widgets(self.tree("Boris"), "drinks")
        soft, wines = drinks["groups"]
        self.assertEqual(
            soft,
            {"title": "Soft drinks", "layout": "inline", "joined": "Still and sparkling water, Lemonade and apple juice", "items": []},
        )
        self.assertEqual((wines["title"], wines["layout"], wines["joined"]), ("Wines", "list", ""))
        self.assertEqual(
            wines["items"][0],
            {"category": "Sparkling", "name": "Example Brut, Riverside Cellars", "line": f"Example Valley{DOT}Chardonnay{DOT}with the starters"},
        )
        self.assertEqual(drinks["list"], [])
        self.assertEqual(drinks["note"], "Cocktails on request")

    def test_a_section_hidden_by_default_and_switched_on_for_one_guest(self):
        menu, guests = fixtures.plain()
        menu["sections"].insert(4, {
            "id": "kids",
            "title": "For the children",
            "visible": False,
            "widgets": [{"type": "text", "text": "Pasta with tomato sauce on request."}],
        })
        guests[0]["sections"] = {"kids": {"visible": True}}
        trees, _report = build(menu, guests)
        self.assertIsNotNone(section(guest_tree(trees, guests, "Lev"), "kids"))
        self.assertIsNone(section(guest_tree(trees, guests, "Rita"), "kids"))
        self.assertIsNotNone(section(trees.staff.tree, "kids"))
        guests[0]["sections"] = {}
        trees, _report = build(menu, guests)
        self.assertIsNone(section(trees.staff.tree, "kids"))


# --------------------------------------------------------------------------
# The staff page
# --------------------------------------------------------------------------


class StaffPageTest(unittest.TestCase):
    def setUp(self):
        self.trees, self.menu, self.guests = reserved19_trees()
        self.tree = self.trees.staff.tree

    def test_staff_page_record_and_root(self):
        self.assertEqual((self.trees.staff.number, self.trees.staff.token), (13, self.guests[12]["token"]))
        self.assertTrue(self.tree["isStaff"])
        self.assertEqual(self.tree["staff"], fixtures.STAFF)

    def test_counters(self):
        self.assertEqual(
            self.tree["counters"],
            {"guests": 18, "notes": 7, "guestsText": "18 guests", "notesText": "7 dietary notes", "tableLabel": "L-shaped table"},
        )
        trees, _report = build(*fixtures.mockup16())
        self.assertEqual(
            trees.staff.tree["counters"],
            {"guests": 14, "notes": 5, "guestsText": "14 guests", "notesText": "5 dietary notes", "tableLabel": "L-shaped table"},
        )

    def test_rows_with_the_reserved_and_the_free_seats(self):
        rows = seating(self.tree)["rows"]
        self.assertEqual([row["number"] for row in rows], list(range(1, 20)))
        free = {"name": "", "isPlusOne": False, "hostName": "", "roleLabel": "", "isCouple": False, "isFree": True, "tags": []}
        self.assertEqual(rows[12], {"number": 13, **free})
        self.assertEqual([row["number"] for row in rows if row["isFree"]], [13])
        trees, _report = build(*fixtures.mockup16())
        self.assertEqual([row["number"] for row in seating(trees.staff.tree)["rows"] if row["isFree"]], [12, 13])

    def test_rows_of_the_people(self):
        rows = {row["number"]: row for row in seating(self.tree)["rows"]}
        self.assertEqual((rows[1]["name"], rows[1]["isPlusOne"], rows[1]["hostName"]), ("Hugo", True, "Greta"))
        self.assertEqual((rows[9]["name"], rows[9]["isPlusOne"], rows[9]["hostName"]), ("", True, "Olga"))
        self.assertEqual((rows[19]["name"], rows[19]["isPlusOne"], rows[19]["hostName"]), ("Greta", False, ""))
        self.assertEqual((rows[2]["name"], rows[3]["name"], rows[3]["tags"]), ("Peggy", "Victor", ["vegan"]))
        self.assertEqual((rows[6]["name"], rows[6]["roleLabel"], rows[6]["isCouple"]), ("Vera", "bride", True))
        self.assertEqual(rows[7]["tags"], ["no gluten"])
        self.assertEqual(rows[10]["tags"], ["no gluten", "no lactose"])

    def test_legend_and_badges_in_the_order_of_the_legend(self):
        menu, guests = fixtures.reserved19()
        record = next(item for item in guests if item.get("name") == "Egor")
        record["seats"][0]["requirements"] = ["lactose", "gluten"]
        menu["requirements"]["gluten"]["tag"] = "gluten-free"
        trees, _report = build(menu, guests)
        widget = seating(trees.staff.tree)
        self.assertEqual([item["letter"] for item in widget["legend"]], ["N", "G", "L", "V", "A"])
        self.assertEqual(widget["legend"][1], {"letter": "G", "label": "no gluten"})
        rows = {row["number"]: row for row in widget["rows"]}
        self.assertEqual(rows[10]["tags"], ["gluten-free", "no lactose"])
        scheme = widget["scheme"]
        self.assertTrue(scheme["hidden"])
        self.assertEqual(scheme["labels"], [])
        self.assertEqual(scheme["mine"], "")
        flagged = sorted(int(seat["number"]) for seat in scheme["seats"] if seat["mark"] == "flagged")
        self.assertEqual(flagged, [3, 4, 7, 10, 11, 14, 18])
        self.assertEqual([badge["letter"] for badge in scheme["badges"]], ["V", "N", "G", "G", "L", "A", "L", "V"])
        # a requirement no seat has is left out of the legend
        record["seats"][0]["requirements"] = []
        del guests[6]["seats"][0]["requirements"]  # the seat with 'no alcohol'
        trees, _report = build(menu, guests)
        self.assertEqual([item["letter"] for item in seating(trees.staff.tree)["legend"]], ["N", "G", "L", "V"])

    def test_staff_titles_and_eyebrows(self):
        titles = [(item["id"], item["title"], item["eyebrow"]) for item in self.tree["sections"]]
        self.assertEqual(
            titles,
            [
                ("cover", "", ""),
                ("seats", "Seating and dietary notes", ""),
                ("starters", "Starters", f"Shared plates{DOT}on the table by 19:15"),
                ("main", "Main course", f"Two sets{DOT}guests choose at the table"),
                ("drinks", "Drinks", "What to serve and when"),
            ],
        )
        self.assertEqual(seating(self.tree)["footnote"], "Seat 13 stays free all evening: keep its place setting.")

    def test_the_dish_for_the_staff_only(self):
        staff_widgets = section(self.tree, "starters")["widgets"]
        self.assertEqual([w["title"] for w in staff_widgets], ["", "On request"])
        (melon,) = staff_widgets[1]["items"]
        self.assertEqual(
            melon,
            {
                "name": "Melon with mint",
                "ingredients": "Melon, mint, lime",
                "allergens": [],
                "tags": "",
                "noRestrictions": True,
                "swapLines": [],
                "note": "Only when a guest asks for something else",
            },
        )
        for page in self.trees.guests:
            self.assertNotIn("Melon", json.dumps(page.tree))
        self.assertIn("melon", self.trees.usage.dishes)
        self.assertIn("melon", self.trees.usage.staff_dishes)

    def test_dish_lines(self):
        bruschetta, cheese, hummus = section(self.tree, "starters")["widgets"][0]["items"]
        self.assertEqual(bruschetta["swapLines"], [f"Seats 7 & 10{DASH}serve the tomatoes on cucumber slices"])
        self.assertEqual(cheese["allergens"], ["lactose", "nuts"])
        self.assertEqual(
            cheese["swapLines"],
            [
                f"Seat 4{DASH}serve a portion without walnuts on a separate plate",
                f"Seats 10 & 14{DASH}bring the fruit plate instead",
            ],
        )
        self.assertEqual((hummus["tags"], hummus["noRestrictions"]), (f"vegan{DOT}gluten-free", False))

    def test_set_lines_and_notes(self):
        (sets,) = widgets(self.tree, "sets")
        fish, meat = sets["items"]
        self.assertEqual(
            fish["swapLines"],
            [
                f"If chosen by seat 4 (no nuts){DASH}serve the second course without the crust.",
                f"By seats 10 & 14 (no lactose){DASH}serve the first course without sour cream.",
            ],
        )
        self.assertEqual(
            meat["swapLines"],
            [
                f"If chosen by seats 3 & 18 (vegan){DASH}serve the roasted roots with lentils instead.",
                f"By seats 7 & 10 (no gluten){DASH}serve the first course without croutons.",
            ],
        )
        self.assertEqual(fish["courses"][0]["allergens"], ["lactose"])
        self.assertEqual(fish["courses"][0]["swapLines"], [])
        self.assertEqual(sets["note"], "Take the orders once the starters are on the table.")

    def test_drink_lines_and_notes(self):
        (drinks,) = widgets(self.tree, "drinks")
        self.assertEqual(drinks["groups"], [])
        self.assertEqual([item["name"] for item in drinks["list"]][:2], ["Example Brut, Riverside Cellars", "Example White, Hillside Estate"])
        self.assertEqual(
            drinks["list"][0]["line"],
            f"with the starters{DOT}6 bottles{DOT}well chilled{DOT}seat 11{DASH}alcohol-free sparkling",
        )
        self.assertEqual(drinks["list"][3], {"category": "Soft", "name": "Still and sparkling water", "line": ""})
        self.assertEqual(drinks["note"], "The bar mixes cocktails on request.")
        trees, _report = build(*fixtures.mockup16())
        (drinks,) = widgets(trees.staff.tree, "drinks")
        self.assertTrue(drinks["list"][0]["line"].endswith(f"seat 1{DASH}no alcohol"))


# --------------------------------------------------------------------------
# Without a table, without a scheme, a plan that does not fit
# --------------------------------------------------------------------------


class OptionsTest(unittest.TestCase):
    def test_without_a_table(self):
        menu, guests = fixtures.plain()
        trees, _report = build(menu, guests)
        widget = seating(guest_tree(trees, guests, "Klara"))
        self.assertIsNone(widget["scheme"])
        self.assertEqual((widget["seatLabel"], widget["whoLabel"]), ("Seats 2 & 3", "Klara and your guest"))
        staff = seating(trees.staff.tree)
        self.assertIsNone(staff["scheme"])
        self.assertEqual(staff["legend"], [])
        self.assertEqual([(row["number"], row["name"], row["isFree"]) for row in staff["rows"]],
                         [(1, "Lev", False), (2, "Klara", False), (3, "", False), (4, "Rita", False)])
        self.assertEqual(trees.staff.tree["counters"]["tableLabel"], "")
        self.assertEqual(trees.staff.tree["counters"]["notesText"], "")

    def test_scheme_legend_and_table_can_be_switched_off(self):
        menu, guests = fixtures.reserved19()
        menu["sections"][1]["widgets"][0].update(showScheme=False, showLegend=False, showTable=False)
        trees, _report = build(menu, guests)
        self.assertIsNone(seating(trees.guests[0].tree)["scheme"])
        staff = seating(trees.staff.tree)
        self.assertEqual((staff["scheme"], staff["legend"], staff["rows"]), (None, [], []))

    def test_a_plan_without_room_for_a_label_is_an_error_of_the_record(self):
        menu, guests = fixtures.plain()
        menu["table"] = {
            "label": "Two narrow arms",
            "arms": [
                {"id": "west", "x": 48, "y": 37, "width": 20, "height": 233},
                {"id": "east", "x": 172, "y": 37, "width": 20, "height": 233},
            ],
            "seats": [
                {"arm": "west", "side": "right", "count": 3},
                {"arm": "west", "side": "left", "count": 3},
                {"arm": "east", "side": "left", "count": 3},
            ],
        }
        guests[:3] = [
            {"token": "lynx-5qd8", "name": "Lev", "seats": [{"number": 5}, {"number": 2, "plusOne": True}]},
            {"token": "badger-8wt4", "name": "Rita", "seats": [{"number": 7}]},
        ]
        report = _core.Report()
        index = _schema.check_data(menu, guests, report)
        self.assertEqual(report.errors, [])
        trees = _page.build_trees(menu, guests, report)
        self.assertEqual(report.errors, ["guests.json: guest #1: seat 2: no room for the '+1' label"])
        self.assertEqual([page.number for page in trees.guests], [2])
        self.assertIsNotNone(trees.staff)
        self.assertTrue(index.ok)

    def test_settings_reach_the_root(self):
        settings = _page.Settings(assets_path="/menu/assets", theme_color="#123456")
        trees, _report = build(*fixtures.plain(), settings)
        for tree in [page.tree for page in trees.guests] + [trees.staff.tree]:
            self.assertEqual(
                (tree["assetsPath"], tree["faviconPath"], tree["themeColor"]),
                ("/menu/assets", "/menu/assets/favicon.svg", "#123456"),
            )

    def test_without_a_staff_record_the_staff_parts_still_count_as_shown(self):
        menu, guests = fixtures.reserved19()
        del guests[12]
        trees, report = build(menu, guests)
        self.assertIsNone(trees.staff)
        self.assertIn("melon", trees.usage.dishes)
        self.assertFalse([w for w in report.warnings if "not shown" in w])

    def test_trees_are_the_same_on_every_build(self):
        first, _report = build(*fixtures.reserved19())
        second, _report = build(*fixtures.reserved19())
        self.assertEqual(json.dumps(first.guests, sort_keys=True), json.dumps(second.guests, sort_keys=True))
        self.assertEqual(json.dumps(first.staff, sort_keys=True), json.dumps(second.staff, sort_keys=True))

    def test_building_does_not_change_the_data(self):
        menu, guests = fixtures.reserved19()
        before = copy.deepcopy((menu, guests))
        build(menu, guests)
        self.assertEqual((menu, guests), before)


# --------------------------------------------------------------------------
# The fields of every node
# --------------------------------------------------------------------------

ROOT_FIELDS = {"isStaff", "coupleNames", "event", "assetsPath", "faviconPath", "themeColor", "staff", "counters", "nav",
               "sections"}
NAV_FIELDS = {"label", "target"}
EVENT_FIELDS = {"title", "when", "place"}
STAFF_FIELDS = {"updated", "contact", "reminder"}
COUNTER_FIELDS = {"guests", "notes", "guestsText", "notesText", "tableLabel"}
SECTION_FIELDS = {"id", "type", "domId", "titleId", "title", "eyebrow", "note", "widgets"}
WIDGET_BASE = {"type", "domId", "labelledBy"}
WIDGET_FIELDS = {
    "text": {"text", "variant"},
    "seating": {"scheme", "mySeats", "seatLabel", "whoLabel", "legend", "rows", "footnote"},
    "dishes": {"title", "items"},
    "sets": {"items", "note", "count", "multiple"},
    "drinks": {"groups", "list", "note"},
    "heading": {"titleId", "title", "eyebrow"},
}
MY_SEAT_FIELDS = {"number", "mark"}
LEGEND_FIELDS = {"letter", "label"}
ROW_FIELDS = {"number", "name", "isPlusOne", "hostName", "roleLabel", "isCouple", "isFree", "tags"}
DISH_FIELDS = {"name", "ingredients", "allergens", "tags", "noRestrictions", "swapLines", "note"}
SET_FIELDS = {"id", "domId", "title", "hint", "eyebrow", "courses", "pairing", "swapLines", "nested"}
GROUP_FIELDS = {"title", "layout", "joined", "items"}
DRINK_FIELDS = {"category", "name", "line"}
SCHEME_FIELDS = {"width", "height", "hidden", "tableLabel", "total", "mine", "single", "outline", "couple", "seats", "badges", "labels"}


class ContractTest(unittest.TestCase):
    """Every node of every tree has exactly the fields of the contract, of
    the right types."""

    def assert_fields(self, node: dict, fields: set, where: str) -> None:
        self.assertIsInstance(node, dict, where)
        self.assertEqual(set(node), fields, where)

    def assert_strings(self, node: dict, keys, where: str) -> None:
        for key in keys:
            self.assertIsInstance(node[key], str, f"{where}.{key}")

    def check_tree(self, tree: dict, where: str) -> None:
        self.assert_fields(tree, ROOT_FIELDS, where)
        self.assertIsInstance(tree["isStaff"], bool)
        self.assert_fields(tree["event"], EVENT_FIELDS, where)
        self.assert_fields(tree["staff"], STAFF_FIELDS, where)
        self.assert_fields(tree["counters"], COUNTER_FIELDS, where)
        self.assert_strings(tree, ("coupleNames", "assetsPath", "faviconPath", "themeColor"), where)
        for item in tree["sections"]:
            self.assert_fields(item, SECTION_FIELDS, where)
            self.assertIn(item["type"], ("cover", "custom"))
            self.assert_strings(item, ("id", "domId", "titleId", "title", "eyebrow", "note"), where)
            for widget in item["widgets"]:
                self.check_widget(widget, f"{where}/{widget['domId']}")
        # a link of the line leads to a section of the page, in their order
        dom_ids = [item["domId"] for item in tree["sections"]]
        for item in tree["nav"]:
            self.assert_fields(item, NAV_FIELDS, where)
            self.assert_strings(item, ("label", "target"), where)
            self.assertTrue(item["label"], where)
        targets = [item["target"] for item in tree["nav"]]
        self.assertEqual(targets, [dom_id for dom_id in dom_ids if dom_id in targets], where)

    def check_widget(self, widget: dict, where: str) -> None:
        kind = widget["type"]
        self.assert_fields(widget, WIDGET_BASE | WIDGET_FIELDS[kind], where)
        if kind == "text":
            self.assertIn(widget["variant"], ("body", "lead", "card", "signature"))
        elif kind == "seating":
            if widget["scheme"] is not None:
                self.assert_fields(widget["scheme"], SCHEME_FIELDS, where)
            for item in widget["mySeats"]:
                self.assert_fields(item, MY_SEAT_FIELDS, where)
                self.assertIn(item["mark"], _page.MARKS)
                self.assertIsInstance(item["number"], int)
            for item in widget["legend"]:
                self.assert_fields(item, LEGEND_FIELDS, where)
            for item in widget["rows"]:
                self.assert_fields(item, ROW_FIELDS, where)
                self.assertIsInstance(item["number"], int)
                self.assertIsInstance(item["tags"], list)
        elif kind == "dishes":
            for item in widget["items"]:
                self.check_dish(item, where)
        elif kind == "sets":
            self.assertEqual(widget["count"], len(widget["items"]))
            self.assertEqual(widget["multiple"], len(widget["items"]) > 1)
            for item in widget["items"]:
                self.assert_fields(item, SET_FIELDS, where)
                self.assertIsInstance(item["nested"], bool)
                for course in item["courses"]:
                    self.check_dish(course, where)
        elif kind == "heading":
            self.assertEqual(widget["titleId"], f"{widget['domId']}--title", where)
            self.assert_strings(widget, ("title", "eyebrow"), where)
            self.assertTrue(widget["title"], where)
        elif kind == "drinks":
            for group in widget["groups"]:
                self.check_group(group, where)
            for item in widget["list"]:
                self.assert_fields(item, DRINK_FIELDS, where)

    def check_group(self, group: dict, where: str) -> None:
        """A group of drinks: a `list` has its items and no line, an `inline`
        group its line and no items."""
        self.assert_fields(group, GROUP_FIELDS, where)
        self.assertIn(group["layout"], ("list", "inline"))
        if group["layout"] == "list":
            self.assertEqual(group["joined"], "", where)
            self.assertTrue(group["items"], where)
        else:
            self.assertEqual(group["items"], [], where)
            self.assertTrue(group["joined"], where)
        for item in group["items"]:
            self.assert_fields(item, DRINK_FIELDS, where)

    def check_dish(self, dish: dict, where: str) -> None:
        self.assert_fields(dish, DISH_FIELDS, where)
        self.assert_strings(dish, ("name", "ingredients", "tags", "note"), where)
        self.assertIsInstance(dish["noRestrictions"], bool)

    def test_every_tree_of_every_fixture(self):
        for name, make in fixtures.SETS.items():
            trees, _report = build(*make())
            for page in trees.guests:
                with self.subTest(fixture=name, page=page.number):
                    self.check_tree(page.tree, f"{name}#{page.number}")
            with self.subTest(fixture=name, page="staff"):
                self.check_tree(trees.staff.tree, f"{name}#staff")

    def test_both_layouts_of_a_group_of_drinks(self):
        layouts = set()
        for name, make in fixtures.SETS.items():
            menu, guests = make()
            trees, _report = build(menu, guests)
            for page in trees.guests:
                for widget in widgets(page.tree, "drinks"):
                    for group in widget["groups"]:
                        with self.subTest(fixture=name, page=page.number, layout=group["layout"]):
                            self.check_group(group, name)
                        layouts.add(group["layout"])
        self.assertEqual(layouts, {"list", "inline"})
        # the one widget of drinks of the plain menu: the guest line, the staff note
        menu, guests = fixtures.plain()
        trees, _report = build(menu, guests)
        (guest,) = widgets(trees.guests[0].tree, "drinks")
        self.assertEqual(
            guest["groups"],
            [{"title": "", "layout": "inline", "joined": "Still and sparkling water, Homemade lemonade", "items": []}],
        )
        self.assertEqual(guest["note"], "")
        (staff,) = widgets(trees.staff.tree, "drinks")
        self.assertEqual((staff["groups"], staff["note"]), ([], "Refill the jugs from the bar."))

    def test_every_widget_type_appears_on_some_page(self):
        trees, _report = build(*fixtures.parts())
        seen = set()
        for tree in [page.tree for page in trees.guests] + [trees.staff.tree]:
            seen.update(widget["type"] for item in tree["sections"] for widget in item["widgets"])
        self.assertEqual(seen, set(WIDGET_FIELDS))
        self.assertEqual(set(WIDGET_FIELDS), set(_schema.WIDGET_TYPES))


# --------------------------------------------------------------------------
# The line of the sections
# --------------------------------------------------------------------------


def nav(tree: dict) -> list[tuple[str, str]]:
    return [(item["label"], item["target"]) for item in tree["nav"]]


MAIN_LINE = [("Seats", "s-seats"), ("Food", "s-food"), ("Drinks", "s-drinks"), ("Info", "s-info")]


class NavTest(unittest.TestCase):
    def test_the_line_of_every_page(self):
        menu, guests = fixtures.parts()
        trees, _report = build(menu, guests)
        for page in trees.guests + [trees.staff]:
            with self.subTest(page=page.number):
                self.assertEqual(nav(page.tree), MAIN_LINE)
        # data without labels: no line
        for name in ("mockup16", "reserved19", "plain"):
            trees, _report = build(*fixtures.SETS[name]())
            for page in trees.guests + [trees.staff]:
                with self.subTest(fixture=name, page=page.number):
                    self.assertEqual(page.tree["nav"], [])

    def test_a_section_has_its_link_on_the_pages_that_show_it(self):
        menu, guests = fixtures.parts()
        sections = menu["sections"]
        # the signature for the guests, a section for the staff, one hidden
        # by default and switched on for one guest
        sections[-1]["nav"] = "Thanks"
        sections.insert(4, {"id": "kitchen", "title": "Kitchen", "nav": "Kitchen", "audience": "staff",
                            "widgets": [{"type": "text", "text": "Plates warm by 19:00."}]})
        sections.insert(5, {"id": "kids", "title": "For the children", "nav": "Kids", "visible": False,
                            "widgets": [{"type": "text", "text": "Pasta with tomato sauce on request."}]})
        record = next(item for item in guests if item.get("name") == "Boris")
        record["sections"] = {"kids": {"visible": True}}
        hidden = next(item for item in guests if item.get("name") == "Galina")
        hidden["sections"] = {"info": {"visible": False}}
        trees, _report = build(menu, guests)
        self.assertEqual(nav(guest_tree(trees, guests, "Boris")),
                         MAIN_LINE[:3] + [("Kids", "s-kids"), ("Info", "s-info"), ("Thanks", "s-signature")])
        self.assertEqual(nav(guest_tree(trees, guests, "Galina")), MAIN_LINE[:3] + [("Thanks", "s-signature")])
        self.assertEqual(nav(guest_tree(trees, guests, "Olga")), MAIN_LINE + [("Thanks", "s-signature")])
        self.assertEqual(nav(trees.staff.tree),
                         MAIN_LINE[:3] + [("Kitchen", "s-kitchen"), ("Kids", "s-kids"), ("Info", "s-info")])
        # nobody switches the hidden section on: it is on no page, nor its link
        record["sections"] = {}
        trees, _report = build(menu, guests)
        for page in trees.guests + [trees.staff]:
            self.assertNotIn("Kids", [label for label, _target in nav(page.tree)])

    def test_a_section_left_empty_on_a_page_has_no_link(self):
        menu, guests = fixtures.parts()
        info = menu["sections"][4]
        info["widgets"][1]["id"] = "smoking"
        info["widgets"][3]["id"] = "camera"
        record = next(item for item in guests if item.get("name") == "Boris")
        record["sections"] = {"info": {"widgets": {"smoking": {"visible": False}, "camera": {"visible": False}}}}
        trees, _report = build(menu, guests)
        boris = guest_tree(trees, guests, "Boris")
        self.assertIsNone(section(boris, "info"))
        self.assertEqual(nav(boris), MAIN_LINE[:3])
        # the staff page keeps the section, and its link
        self.assertEqual(nav(trees.staff.tree), MAIN_LINE)

    def test_the_labels_are_shared_texts(self):
        menu, _guests = fixtures.parts()
        public = _page.public_menu(menu)
        self.assertEqual([item.get("nav") for item in public["sections"]],
                         [None, "Seats", "Food", "Drinks", "Info", ""])


# --------------------------------------------------------------------------
# The parts of a section under their headings
# --------------------------------------------------------------------------


def layout(tree: dict, section_id: str) -> list[tuple[str, str]]:
    """(type, domId) of the widgets of a section."""
    found = section(tree, section_id)
    return None if found is None else [(widget["type"], widget["domId"]) for widget in found["widgets"]]


class PartsTest(unittest.TestCase):
    def setUp(self):
        self.menu, self.guests = fixtures.parts()
        self.trees, _report = build(self.menu, self.guests)

    def test_the_parts_of_a_guest_page(self):
        boris = guest_tree(self.trees, self.guests, "Boris")
        # the dishes on request (w3) are for the staff only
        self.assertEqual(layout(boris, "food"), [("heading", "s-food--w1"), ("dishes", "s-food--w2"),
                                                 ("heading", "s-food--w4"), ("sets", "s-food--w5"),
                                                 ("text", "s-food--w6")])
        starters, _dishes, main, sets, _card = section(boris, "food")["widgets"]
        self.assertEqual(starters, {"type": "heading", "domId": "s-food--w1", "labelledBy": "s-food--title",
                                    "titleId": "s-food--w1--title", "title": "Starters",
                                    "eyebrow": "Shared plates for the table"})
        self.assertEqual((main["title"], main["eyebrow"]), ("Main course", "Choose one of two sets"))
        # the sets stand in the second part: labelled by its heading, a level lower
        self.assertEqual(sets["labelledBy"], "s-food--w4--title")
        self.assertEqual([item["nested"] for item in sets["items"]], [True, True])
        self.assertEqual(section(boris, "food")["title"], "Food")
        # the part for the staff only is not on the page of a guest
        self.assertEqual(layout(boris, "info"), [("heading", "s-info--w1"), ("text", "s-info--w2"),
                                                 ("heading", "s-info--w3"), ("text", "s-info--w4")])
        # the card hidden by the record keeps the numbers of the others
        gleb = guest_tree(self.trees, self.guests, "Gleb")
        self.assertEqual([dom_id for _kind, dom_id in layout(gleb, "food")],
                         ["s-food--w1", "s-food--w2", "s-food--w4", "s-food--w5"])

    def test_the_parts_of_the_staff_page(self):
        staff = self.trees.staff.tree
        self.assertEqual(layout(staff, "food"), [("heading", "s-food--w1"), ("dishes", "s-food--w2"),
                                                 ("dishes", "s-food--w3"), ("heading", "s-food--w4"),
                                                 ("sets", "s-food--w5")])
        starters, _dishes, _on_request, main, sets = section(staff, "food")["widgets"]
        # the eyebrows for the staff replace those of the guests, the titles stay
        self.assertEqual((starters["title"], starters["eyebrow"]),
                         ("Starters", "Shared plates · on the table by 19:15"))
        self.assertEqual((main["title"], main["eyebrow"]),
                         ("Main course", "Two sets · guests choose at the table"))
        self.assertEqual(sets["labelledBy"], "s-food--w4--title")
        self.assertEqual({item["nested"] for item in sets["items"]}, {True})
        self.assertEqual([widget["title"] for widget in section(staff, "info")["widgets"]
                          if widget["type"] == "heading"], ["Smoking", "Instant camera", "Clearing up"])
        # a title for the staff replaces the title of the guests there alone
        menu, guests = fixtures.parts()
        menu["sections"][2]["widgets"][0]["staff"]["title"] = "Starters at 19:15"
        trees, _report = build(menu, guests)
        self.assertEqual(section(trees.staff.tree, "food")["widgets"][0]["title"], "Starters at 19:15")
        for page in trees.guests:
            self.assertEqual(section(page.tree, "food")["widgets"][0]["title"], "Starters")

    def test_a_heading_with_nothing_under_it_on_a_page_is_left_out(self):
        menu, guests = fixtures.parts()
        food = menu["sections"][2]["widgets"]
        # over the dishes for the staff only: nothing under it for a guest
        food.insert(2, {"type": "heading", "title": "On request"})
        trees, report = build(menu, guests)
        self.assertEqual(report.warnings, [])
        boris = guest_tree(trees, guests, "Boris")
        self.assertEqual([dom_id for kind, dom_id in layout(boris, "food") if kind == "heading"],
                         ["s-food--w1", "s-food--w5"])
        self.assertEqual([dom_id for kind, dom_id in layout(trees.staff.tree, "food") if kind == "heading"],
                         ["s-food--w1", "s-food--w3", "s-food--w5"])
        # at the end of a section and before another heading: on no page
        menu, guests = fixtures.parts()
        info = menu["sections"][4]["widgets"]
        del info[1]
        info.append({"type": "heading", "title": "Taxis"})
        trees, _report = build(menu, guests)
        for tree in [page.tree for page in trees.guests] + [trees.staff.tree]:
            titles = [widget["title"] for widget in section(tree, "info")["widgets"] if widget["type"] == "heading"]
            self.assertNotIn("Smoking", titles)
            self.assertNotIn("Taxis", titles)

    def test_a_section_of_headings_alone_is_empty(self):
        menu, guests = fixtures.parts()
        menu["sections"].insert(4, {
            "id": "sweets",
            "title": "Sweets",
            "widgets": [{"type": "heading", "title": "Dessert"}, {"type": "text", "id": "cake", "text": "Cake at ten."}],
        })
        record = next(item for item in guests if item.get("name") == "Boris")
        record["sections"] = {"sweets": {"widgets": {"cake": {"visible": False}}}}
        trees, _report = build(menu, guests)
        self.assertIsNone(section(guest_tree(trees, guests, "Boris"), "sweets"))
        self.assertEqual(layout(guest_tree(trees, guests, "Galina"), "sweets"),
                         [("heading", "s-sweets--w1"), ("text", "s-sweets--w2")])
        # with a note of the guest the section stays, the note alone
        record["sections"]["sweets"]["note"] = "We kept a slice for you."
        trees, _report = build(menu, guests)
        sweets = section(guest_tree(trees, guests, "Boris"), "sweets")
        self.assertEqual((sweets["widgets"], sweets["note"]), ([], "We kept a slice for you."))

    def test_a_heading_for_the_staff_only(self):
        menu, guests = fixtures.reserved19()
        menu["sections"][3]["widgets"].insert(0, {"type": "heading", "audience": "staff", "title": "Kitchen"})
        trees, _report = build(menu, guests)
        (guest_sets,) = widgets(guest_tree(trees, guests, "Boris"), "sets")
        self.assertEqual((guest_sets["domId"], guest_sets["labelledBy"]), ("s-main--w2", "s-main--title"))
        self.assertEqual({item["nested"] for item in guest_sets["items"]}, {False})
        self.assertEqual(widgets(guest_tree(trees, guests, "Boris"), "heading"), [])
        (staff_sets,) = widgets(trees.staff.tree, "sets")
        self.assertEqual(staff_sets["labelledBy"], "s-main--w1--title")
        self.assertEqual({item["nested"] for item in staff_sets["items"]}, {True})

    def test_a_heading_a_guest_switches_off(self):
        menu, guests = fixtures.reserved19()
        menu["sections"][3]["widgets"].insert(0, {"type": "heading", "id": "choice", "title": "Main course"})
        record = next(item for item in guests if item.get("name") == "Boris")
        record["sections"] = {"main": {"widgets": {"choice": {"visible": False}}}}
        trees, _report = build(menu, guests)
        (boris_sets,) = widgets(guest_tree(trees, guests, "Boris"), "sets")
        self.assertEqual((boris_sets["labelledBy"], boris_sets["items"][0]["nested"]), ("s-main--title", False))
        (galina_sets,) = widgets(guest_tree(trees, guests, "Galina"), "sets")
        self.assertEqual((galina_sets["labelledBy"], galina_sets["items"][0]["nested"]), ("s-main--w1--title", True))

    def test_the_guest_projection_of_a_heading(self):
        public = _page.public_menu(fixtures.parts()[0])
        food = next(item for item in public["sections"] if item["id"] == "food")
        self.assertEqual(food["widgets"][0], {"type": "heading", "id": None, "visible": True, "title": "Starters",
                                              "eyebrow": "Shared plates for the table"})
        info = next(item for item in public["sections"] if item["id"] == "info")
        # the part for the staff only keeps its places as None
        self.assertEqual([widget and widget["type"] for widget in info["widgets"]],
                         ["heading", "text", "heading", "text", None, None])


if __name__ == "__main__":
    unittest.main()
