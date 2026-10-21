"""The plan of the table on a page: the scheme partial on the objects of the geometry.

The partial `fragments/partials/scheme.html` draws an inline SVG from the
`scheme` object of `menu_tools._table` with the template engine of the
invitations: every number comes from the object, the markup only places it.
The objects here are built by the geometry for four shapes of table - the
L-shaped tables of the data sets on 16 and on 19 seats, a straight table with
the couple facing each other and a U-shaped one with the couple label upright
on a vertical arm - and rendered in the frame the seating widget gives the
partial.  The output goes through the checks of a finished HTML page and of
an SVG file of the invitations builder.

The names in the drawing (the couple label) come from the constants of the
data sets, never from literals here.

The radii the geometry writes depend on the border widths the style sheet
draws, and its field on the size the style sheet gives the drawing: the last
tests tie those constants of `menu_tools._table` to the tokens of
`assets/app.css`.
"""

from __future__ import annotations

import copy
import hashlib
import re
import sys
import unittest
from fractions import Fraction
from html.parser import HTMLParser
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from menu_tools import _core as core  # noqa: E402  (imported after sys.path is prepared)
from menu_tools import _table, _words  # noqa: E402
from tests import fixtures  # noqa: E402
from tests.test_table import straight_table, u_table  # noqa: E402
from tests.test_tokens_sync import token_contexts  # noqa: E402

FRAGMENTS_DIR = ROOT / "fragments"
APP_CSS = ROOT / "assets" / "app.css"
#: The frame of the seating widget around the partial.
FRAME = "<!-- with:scheme --><!-- include:partials/scheme --><!-- endwith -->"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"

#: shape -> (table, couple seats, guest seats (the first one is the guest's
#: own, the others are taken by a +1), letters of the staff by seat number).
SHAPES = {
    "l16": (fixtures.l_table_16, [4, 5], [8, 9],
            {1: ["A"], 3: ["N"], 7: ["V"], 10: ["G", "L"], 14: ["L"]}),
    "l19": (fixtures.l_table_19, [6, 7], [19, 1],
            {3: ["V"], 4: ["N"], 7: ["G"], 10: ["G", "L"], 11: ["A"], 14: ["L"], 18: ["V"]}),
    "straight12": (straight_table, [4, 10], [7, 8], {2: ["N"], 7: ["G", "V"], 12: ["A"]}),
    # the couple sits on the outer side of the west arm: its label stands upright
    "u20": (u_table, [18, 19], [11, 12], {1: ["N"], 8: ["G", "L"], 20: ["A", "N"]}),
}

#: The attributes each element of the drawing may have: geometry, classes and
#: the accessibility of the drawing, nothing else.
ATTRIBUTES = {
    "svg": {"class", "viewbox", "width", "height", "focusable", "role", "aria-label",
            "aria-hidden"},
    "path": {"class", "d"},
    "g": {"class"},
    "circle": {"class", "cx", "cy", "r"},
    "text": {"class", "x", "y", "transform"},
}
#: Every class of the drawing; the modifiers come from the enumerations.
CLASSES = frozenset({
    "scheme", "scheme__table", "scheme__couple", "seat", "seat__ring", "seat__circle",
    "seat__number", "seat-badge", "seat-badge__circle", "seat-badge__letter", "seat-label",
    *(f"seat--{kind}" for kind in _table.KINDS), *(f"seat--{mark}" for mark in _table.MARKS),
    *(f"seat-label--{anchor}" for anchor in _table.ANCHORS),
})
NUMBER = r"-?\d+(?:\.(?:5|25|75))?"
NUMBER_ATTRIBUTES = ("width", "height", "cx", "cy", "r", "x", "y")

#: sha256 of the guest's and the staff markup of the L-shaped table on 16
#: seats: a change of the partial changes it.
DIGEST = "5d74d81275c9bd8f9913d1b9b36124f507931171f8b8344f93ffca51c2a4407d"


def couple(shape: str) -> dict:
    return {"couple_seats": SHAPES[shape][1], "couple_label": fixtures.COUPLE_LABEL,
            "couple_arm": None}


def guest_object(shape: str, own: list | None = None, table: dict | None = None) -> dict:
    """The guest's object; every seat of `own` after the first is a +1."""
    make, _couple, seats, _letters = SHAPES[shape]
    own = seats if own is None else own
    return _table.guest_scheme(table or make(), own_seats=own, plus_one_seats=own[1:],
                               mine_text=_words.mine_text(own), **couple(shape))


def staff_object(shape: str, table: dict | None = None) -> dict:
    make, _couple, _seats, letters = SHAPES[shape]
    return _table.staff_scheme(table or make(), letters=letters, **couple(shape))


_TEMPLATE = core.parse_template(FRAME, "frame", core.load_fragments(FRAGMENTS_DIR))


def render(scheme: dict, staff_page: bool) -> str:
    """The partial for a page of the audience, as the build publishes it."""
    output = _TEMPLATE.render({"isStaff": staff_page, "scheme": scheme})
    return core.strip_html_comments(output, "frame")


def html_page(svg: str) -> str:
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            "<title>Plan</title>\n</head>\n<body>\n" + svg + "</body>\n</html>\n")


def svg_file(svg: str) -> str:
    return svg.replace("<svg ", f'<svg xmlns="{SVG_NAMESPACE}" ', 1)


class Elements(HTMLParser):
    """(tag, attributes, text) of every element of the markup, in order."""

    def __init__(self, markup: str):
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, dict, str]] = []
        self.feed(markup)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.found.append((tag, {name: value or "" for name, value in attrs}, ""))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.found and data.strip():
            tag, attributes, text = self.found[-1]
            self.found[-1] = (tag, attributes, text + data)

    def of_class(self, name: str) -> list[tuple[str, dict, str]]:
        return [item for item in self.found if name in item[1].get("class", "").split()]


def every_drawing():
    """(shape, audience, object, markup) for every shape and both audiences."""
    for shape in SHAPES:
        for staff_page in (False, True):
            scheme = staff_object(shape) if staff_page else guest_object(shape)
            yield shape, "staff" if staff_page else "guest", scheme, render(scheme, staff_page)


# --------------------------------------------------------------------------
# The markup
# --------------------------------------------------------------------------


class MarkupTest(unittest.TestCase):
    def test_every_shape_passes_the_checks_of_a_page_and_of_an_svg(self):
        for shape, audience, _scheme, svg in every_drawing():
            with self.subTest(shape=shape, audience=audience):
                self.assertTrue(svg.startswith('\n<svg class="scheme" viewBox="0 0 318 310" '
                                               'width="318" height="310" focusable="false"'))
                self.assertEqual(core.check_html(html_page(svg), lambda _path: False), [])
                self.assertEqual(core.check_svg(svg_file(svg)), [])
                core.check_rendered(html_page(svg))

    def test_attributes_hold_geometry_classes_and_accessibility_only(self):
        for shape, audience, _scheme, svg in every_drawing():
            with self.subTest(shape=shape, audience=audience):
                for tag, attributes, _text in Elements(svg).found:
                    self.assertIn(tag, ATTRIBUTES)
                    self.assertLessEqual(set(attributes), ATTRIBUTES[tag], tag)
                    self.assertLessEqual(set(attributes["class"].split()), CLASSES)
                for pattern in (r"\sstyle\s*=", r"(?i)<style", r"(?i)<script", r"\shref\s*=",
                                r"(?i)<foreignobject", r"(?i)<title", r"\sid\s*=", r"\sfill\s*=",
                                r"\sstroke", r"\sfont", r"\{\{", r"\}\}"):
                    self.assertNotRegex(svg, pattern)

    def test_numbers_are_whole_half_or_quarter_units(self):
        for shape, audience, _scheme, svg in every_drawing():
            with self.subTest(shape=shape, audience=audience):
                for tag, attributes, _text in Elements(svg).found:
                    for name in NUMBER_ATTRIBUTES:
                        if name in attributes:
                            self.assertRegex(attributes[name], rf"\A{NUMBER}\Z", (tag, name))
                    if "d" in attributes:
                        for token in re.findall(r"[^MLAZ ]+", attributes["d"]):
                            self.assertRegex(token, rf"\A{NUMBER}\Z")
                    if "transform" in attributes:
                        self.assertEqual(attributes["transform"],
                                         f"rotate(-90 {attributes['x']} {attributes['y']})")
                self.assertRegex(svg, r'viewBox="0 0 318 310"')

    def test_the_layers_are_outline_couple_seats_badges_labels(self):
        layers = ("scheme__table", "scheme__couple", "seat", "seat-badge", "seat-label")
        for shape, audience, _scheme, svg in every_drawing():
            with self.subTest(shape=shape, audience=audience):
                order = []
                for _tag, attributes, _text in Elements(svg).found:
                    first = attributes.get("class", "").split()[:1]
                    if first and first[0] in layers and (not order or order[-1] != first[0]):
                        order.append(first[0])
                expected = [layer for layer in layers
                            if layer != ("seat-label" if audience == "staff" else "seat-badge")]
                self.assertEqual(order, expected)

    def test_every_seat_once_with_its_number_at_its_centre(self):
        for shape, audience, scheme, svg in every_drawing():
            with self.subTest(shape=shape, audience=audience):
                elements = Elements(svg)
                numbers = [(attributes["x"], attributes["y"], text)
                           for _tag, attributes, text in elements.of_class("seat__number")]
                self.assertEqual(numbers, [(seat["cx"], seat["cy"], seat["number"])
                                           for seat in scheme["seats"]])
                circles = [(attributes["cx"], attributes["cy"], attributes["r"])
                           for _tag, attributes, _text in elements.of_class("seat__circle")]
                self.assertEqual(circles, [(seat["cx"], seat["cy"], seat["r"])
                                           for seat in scheme["seats"]])
                groups = [attributes["class"]
                          for _tag, attributes, _text in elements.of_class("seat")]
                self.assertEqual(groups, [f"seat seat--{seat['kind']} seat--{seat['mark']}"
                                          for seat in scheme["seats"]])

    def test_the_couple_label_lies_flat_or_stands_upright_on_its_arm(self):
        cases = {"l16": False, "straight12": False, "u20": True}
        for shape, vertical in cases.items():
            for staff_page in (False, True):
                scheme = staff_object(shape) if staff_page else guest_object(shape)
                label = scheme["couple"]
                with self.subTest(shape=shape, staff=staff_page):
                    self.assertIs(label["vertical"], vertical)
                    self.assertEqual(label["text"], fixtures.COUPLE_LABEL.upper())
                    [(tag, attributes, text)] = Elements(render(scheme, staff_page)).of_class(
                        "scheme__couple")
                    self.assertEqual((attributes["x"], attributes["y"], text),
                                     (label["x"], label["y"], label["text"]))
                    self.assertEqual(attributes.get("transform"),
                                     f"rotate(-90 {label['x']} {label['y']})" if vertical else None)
        # no couple label: no text in the arm
        scheme = _table.guest_scheme(fixtures.l_table_16(), own_seats=[8], plus_one_seats=[],
                                     mine_text="8", couple_seats=[4, 5], couple_label=None,
                                     couple_arm=None)
        self.assertNotIn("scheme__couple", render(scheme, False))

    def test_the_markup_keeps_one_line_per_layer_and_seat(self):
        svg = render(guest_object("l16"), False)
        lines = svg.strip("\n").split("\n")
        # the svg tag, the outline, the couple label, 16 seats, 2 labels, the end
        self.assertEqual(len(lines), 1 + 1 + 1 + 16 + 2 + 1)
        self.assertNotRegex(svg, r">[ \t]+<")
        self.assertEqual(lines[-1], "</svg>")

    def test_the_digest_of_the_markup_is_fixed(self):
        text = render(guest_object("l16"), False) + render(staff_object("l16"), True)
        self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), DIGEST)


# --------------------------------------------------------------------------
# The guest and the staff
# --------------------------------------------------------------------------


def svg_tag(svg: str) -> dict:
    return Elements(svg).found[0][1]


class GuestTest(unittest.TestCase):
    def test_the_drawing_is_one_image_named_after_the_table_and_the_seats(self):
        cases = (([8], "Table plan: L-shaped table, 16 seats. Your seat: 8"),
                 ([8, 9], "Table plan: L-shaped table, 16 seats. Your seats: 8 and 9"),
                 ([8, 9, 10], "Table plan: L-shaped table, 16 seats. Your seats: 8, 9 and 10"))
        for own, name in cases:
            with self.subTest(own=own):
                tag = svg_tag(render(guest_object("l16", own), False))
                self.assertEqual(tag["role"], "img")
                self.assertEqual(tag["aria-label"], name)
                self.assertEqual(tag["focusable"], "false")
                self.assertNotIn("aria-hidden", tag)

    def test_the_guest_sees_no_dietary_marks(self):
        for shape in SHAPES:
            svg = render(guest_object(shape), False)
            with self.subTest(shape=shape):
                for part in ("aria-hidden", "seat-badge", "seat--flagged"):
                    self.assertNotIn(part, svg)

    def test_rings_on_the_own_seats_and_the_labels_where_the_object_puts_them(self):
        for shape in SHAPES:
            scheme = guest_object(shape)
            elements = Elements(render(scheme, False))
            own = [seat for seat in scheme["seats"] if seat["kind"] == "you"]
            with self.subTest(shape=shape):
                rings = [(attributes["cx"], attributes["cy"], attributes["r"])
                         for _tag, attributes, _text in elements.of_class("seat__ring")]
                self.assertEqual(rings, [(seat["cx"], seat["cy"], seat["ringR"]) for seat in own])
                self.assertEqual(len(own), 2)
                labels = [(attributes["class"], attributes["x"], attributes["y"], text)
                          for _tag, attributes, text in elements.of_class("seat-label")]
                self.assertEqual(labels, [
                    (f"seat-label seat-label--{label['anchor']}", label["x"], label["y"],
                     "You" if label["isYou"] else "+1")
                    for label in scheme["labels"]])
                self.assertEqual([text for *_rest, text in labels], ["You", "+1"])

    def test_more_than_two_own_seats_get_rings_and_no_labels(self):
        scheme = guest_object("l16", [8, 9, 10])
        svg = render(scheme, False)
        self.assertEqual(svg.count('class="seat__ring"'), 3)
        self.assertEqual(svg.count("seat seat--you "), 3)
        self.assertNotIn("seat-label", svg)


class StaffTest(unittest.TestCase):
    def test_the_drawing_is_hidden_from_screen_readers(self):
        for shape in SHAPES:
            svg = render(staff_object(shape), True)
            tag = svg_tag(svg)
            with self.subTest(shape=shape):
                self.assertEqual(tag["aria-hidden"], "true")
                self.assertEqual(tag["focusable"], "false")
                self.assertNotIn("role", tag)
                self.assertNotIn("aria-label", tag)
                for part in ("seat--you", "seat__ring", "seat-label", "Your seat"):
                    self.assertNotIn(part, svg)

    def test_a_badge_per_letter_and_a_flagged_seat_per_note(self):
        for shape in SHAPES:
            letters = SHAPES[shape][3]
            scheme = staff_object(shape)
            elements = Elements(render(scheme, True))
            with self.subTest(shape=shape):
                badges = [(attributes["x"], attributes["y"], text)
                          for _tag, attributes, text in elements.of_class("seat-badge__letter")]
                self.assertEqual([text for *_xy, text in badges],
                                 [letter for number in sorted(letters)
                                  for letter in letters[number]])
                self.assertEqual(badges, [(badge["cx"], badge["cy"], badge["letter"])
                                          for badge in scheme["badges"]])
                circles = [(attributes["cx"], attributes["cy"], attributes["r"])
                           for _tag, attributes, _text in elements.of_class("seat-badge__circle")]
                self.assertEqual(circles, [(badge["cx"], badge["cy"], badge["r"])
                                           for badge in scheme["badges"]])
                marked = [number for number, (_tag, attributes, _text)
                          in enumerate(elements.of_class("seat"), start=1)
                          if "seat--flagged" in attributes["class"].split()]
                self.assertEqual(marked, sorted(letters))


# --------------------------------------------------------------------------
# Values from the data and the branches of the audiences
# --------------------------------------------------------------------------


class SafetyTest(unittest.TestCase):
    def test_the_table_label_and_the_couple_label_are_escaped(self):
        value = '<b>"x"&{{y}}'
        table = fixtures.l_table_16()
        table["label"] = value
        scheme = _table.guest_scheme(table, own_seats=[8], plus_one_seats=[], mine_text="8",
                                     couple_seats=[4, 5], couple_label=value, couple_arm=None)
        svg = render(scheme, False)
        self.assertIn('aria-label="Table plan: &lt;b&gt;&quot;x&quot;&amp;&#123;&#123;y&#125;'
                      '&#125;, 16 seats. Your seat: 8"', svg)
        self.assertIn(">&lt;B&gt;&quot;X&quot;&amp;&#123;&#123;Y&#125;&#125;</text>", svg)
        self.assertNotIn("<b>", svg.lower())
        self.assertEqual(core.check_html(html_page(svg), lambda _path: False), [])
        self.assertEqual(core.check_svg(svg_file(svg)), [])

    def test_the_branches_of_the_audiences_guard_against_a_wrong_object(self):
        # a guest's page never prints badges, even when the object had them
        guest = guest_object("l16")
        guest["badges"] = copy.deepcopy(staff_object("l16")["badges"])
        svg = render(guest, False)
        self.assertNotIn("seat-badge", svg)
        self.assertEqual(svg_tag(svg)["role"], "img")
        # the staff page never prints labels nor names the guest's seats
        staff = staff_object("l16")
        staff.update(labels=copy.deepcopy(guest["labels"]), mine="8 and 9", single=False,
                     hidden=False)
        svg = render(staff, True)
        self.assertNotIn("seat-label", svg)
        self.assertNotIn("Your seat", svg)
        self.assertNotIn("role", svg_tag(svg))


# --------------------------------------------------------------------------
# The numbers of the geometry and the tokens of the style sheet
# --------------------------------------------------------------------------


def px(value: str) -> Fraction:
    """`1.5px` -> 3/2; anything else fails."""
    match = re.fullmatch(r"(\d+(?:\.\d+)?)px", value)
    if match is None:
        raise AssertionError(f"not a length in px: {value!r}")
    return Fraction(match.group(1))


def token_ties(css: str) -> list[str]:
    """Where the constants of the geometry and the tokens of `css` disagree.

    The build computes the radii of the seats from the border widths, so the
    circle of a seat stays 30 (34) units across whatever the style sheet
    draws; the field is the viewBox the style sheet sizes.
    """
    tokens = token_contexts(css)[""]
    seat, flag = px(tokens["--line-width-seat"]), px(tokens["--line-width-flag"])
    width, height = (Fraction(part) for part in tokens["--seating-ratio"].split("/"))
    half = Fraction(1, 2)
    expected = {
        "--line-width-seat": (seat, Fraction(_table.SEAT_STROKE)),
        "--line-width-flag": (flag, Fraction(_table.FLAG_STROKE)),
        "--seating-width": (px(tokens["--seating-width"]), Fraction(_table.FIELD_WIDTH)),
        "--seating-ratio": (width / height, Fraction(_table.FIELD_WIDTH, _table.FIELD_HEIGHT)),
        "SEAT_R": (Fraction(_table.SEAT_R), _table.SEAT_DIAMETER * half - seat * half),
        "FLAG_R": (Fraction(_table.FLAG_R), _table.SEAT_DIAMETER * half - flag * half),
        "YOU_R": (Fraction(_table.YOU_R), _table.YOU_DIAMETER * half - seat * half),
        "RING_R": (Fraction(_table.RING_R), _table.YOU_DIAMETER * half + _table.RING_WIDTH),
    }
    return [f"{name}: {actual} against {wanted}"
            for name, (actual, wanted) in expected.items() if actual != wanted]


class TokenTieTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = APP_CSS.read_text(encoding="utf-8")

    def test_the_constants_of_the_geometry_follow_the_tokens(self):
        self.assertEqual(token_ties(self.css), [])

    def test_a_drift_on_either_side_is_caught(self):
        for old, new, name in (("--line-width-seat: 1.5px;", "--line-width-seat: 2px;", "SEAT_R"),
                               ("--line-width-flag: 2.5px;", "--line-width-flag: 3px;", "FLAG_R"),
                               ("--seating-width: 318px;", "--seating-width: 320px;",
                                "--seating-width"),
                               ("--seating-ratio: 318 / 310;", "--seating-ratio: 4 / 3;",
                                "--seating-ratio")):
            with self.subTest(token=old):
                self.assertEqual(self.css.count(old), 1)
                problems = token_ties(self.css.replace(old, new))
                self.assertTrue(problems)
                self.assertTrue(any(problem.startswith(name) for problem in problems), problems)
        for constant, value in (("SEAT_STROKE", "2"), ("YOU_R", "16"), ("RING_WIDTH", 5),
                                ("FIELD_HEIGHT", 300)):
            with self.subTest(constant=constant), mock.patch.object(_table, constant, value):
                self.assertTrue(token_ties(self.css))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
