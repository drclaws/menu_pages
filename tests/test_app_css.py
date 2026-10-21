"""Static checks of the style sheet: sections, raw values, sources, sets, print."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_CSS = ROOT / "assets" / "app.css"

#: The numbered sections, in their order.
SECTIONS = (
    ("1", "Tokens"),
    ("1a", "Menu tokens"),
    ("2", "Fonts"),
    ("3", "Base"),
    ("4", "Layout primitives"),
    ("5", "Components"),
    ("5a", "Page"),
    ("6", "Scheme"),
    ("7", "Motion & reveal"),
    ("8", "Print"),
)

#: The sections where raw values (colours, lengths, durations) belong.
TOKEN_SECTIONS = ("1", "1a")

SECTION_RE = re.compile(r"^/\* =+\n   (\d+a?)\. (.+)$", re.MULTILINE)
RAW_VALUE_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla|oklch|color-mix)\("
                          r"|(?<![\w.#-])\d*\.?\d+(?:px|rem|em|ms|s|vw|vh|svh|dvh)\b")
CONDITION_RE = re.compile(r"@media|@container|@supports")
PANELS = "html.js .sets__tabs:not([hidden]) ~ .sets__panels"


def strip_comments(css):
    """The CSS without comments; line breaks are kept, so line numbers stay."""
    return re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group(0).count("\n"), css, flags=re.S)


def rules(css):
    """{selector: body} of the innermost rules, whitespace collapsed (the first one wins)."""
    found = {}
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        found.setdefault(" ".join(selector.split()), " ".join(body.split()))
    return found


def section_texts(css):
    """{"1": (first line, text), ...}: each numbered section up to the next one."""
    marks = list(SECTION_RE.finditer(css))
    texts = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(css)
        texts[mark.group(1)] = (css.count("\n", 0, mark.start()), css[mark.start():end])
    return texts


def media_blocks(css, condition):
    """The bodies of every `@media <condition> { ... }` block (one level of nesting)."""
    pattern = r"@media %s\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}" % re.escape(condition)
    return re.findall(pattern, css)


class StyleSheetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = APP_CSS.read_text(encoding="utf-8")
        cls.code = strip_comments(cls.raw)
        cls.marks = [(mark.group(1), mark.group(2).strip()) for mark in SECTION_RE.finditer(cls.raw)]
        cls.sections = section_texts(cls.raw)

    def section_code(self, number):
        return strip_comments(self.sections[number][1])

    def test_sections_are_in_place_and_in_order(self):
        self.assertEqual(self.marks, list(SECTIONS))

    def test_the_header_lists_every_section(self):
        header = self.raw[:self.raw.index("*/") + 2]
        positions = []
        for number, name in SECTIONS:
            with self.subTest(section=number):
                match = re.search(r"\n\s+%s\.\s+%s\s+- " % (re.escape(number), re.escape(name)), header)
                self.assertIsNotNone(match)
                positions.append(match.start())
        self.assertEqual(positions, sorted(positions))

    def test_no_raw_values_outside_the_token_sections(self):
        bad = []
        for number, (first_line, text) in self.sections.items():
            if number in TOKEN_SECTIONS:
                continue
            for offset, line in enumerate(strip_comments(text).split("\n")):
                if not CONDITION_RE.search(line) and RAW_VALUE_RE.search(line):
                    bad.append((first_line + offset + 1, line.strip()))
        self.assertEqual(bad, [])
        # what comes before the first section is the header comment only
        first = self.raw.index(self.sections["1"][1])
        self.assertEqual(strip_comments(self.raw[:first]).strip(), "")

    def test_condition_numbers_match_their_tokens(self):
        # var() does not work in conditions: each number is repeated from a
        # token, and the comment right above names the token and its value
        conditions = list(re.finditer(r"@(?:media|container)[^{]*?\((?:min|max)-width:\s*([\d.]+\w+)\)",
                                      self.code))
        self.assertTrue(conditions)
        for condition in conditions:
            with self.subTest(condition=condition.group(0)):
                before = self.raw[:self.raw.index(condition.group(0))]
                comment = before[before.rindex("/*"):]
                named = re.search(r"(--[\w-]+) = ([\d.]+\w+)", comment)
                self.assertIsNotNone(named, comment)
                self.assertEqual(named.group(2), condition.group(1))
                token = re.search(r"\n\s*%s:\s*([^;]+);" % re.escape(named.group(1)), self.code)
                self.assertEqual(token.group(1).strip(), condition.group(1))

    def test_nothing_is_loaded_from_elsewhere(self):
        for pattern in (r"@import\b", r"\burl\(", r"@font-face\b", r"\bimage-set\(",
                        r"(?i)https?:", r"//"):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.code, pattern)

    def test_hover_only_inside_hover_media_query(self):
        outside = re.sub(r"@media \(hover: hover\)\s*\{(?:[^{}]*\{[^{}]*\})*\s*\}", "", self.code)
        self.assertNotIn(":hover", outside)
        self.assertIn(".sets__tab:hover", self.code)

    def test_the_scheme_section_has_no_rules_yet(self):
        self.assertEqual(self.section_code("6").strip(), "")

    def test_hidden_beats_the_display_of_components(self):
        self.assertEqual(rules(self.section_code("3"))["[hidden]"], "display: none !important;")


class SetSwitcherStylesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = APP_CSS.read_text(encoding="utf-8")
        cls.code = strip_comments(raw)
        sections = section_texts(raw)
        cls.components = strip_comments(sections["5"][1])
        cls.print = strip_comments(sections["8"][1])

    def test_without_the_script_the_cards_follow_each_other(self):
        found = rules(self.components)
        self.assertEqual(found[".sets__panel + .sets__panel"], "margin-block-start: var(--space-lg);")
        # nothing hides a card or the room of a card unless the script runs
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", self.code):
            if re.search(r"visibility:\s*hidden|grid-area", body):
                with self.subTest(selector=selector.strip()):
                    self.assertTrue(" ".join(selector.split()).startswith(PANELS + " >"))

    def test_with_the_script_the_cards_share_one_cell(self):
        found = rules(self.components)
        self.assertEqual(found[PANELS], "display: grid; grid-template-columns: minmax(0, 1fr); "
                                        "margin-block-start: var(--space-md);")
        self.assertEqual(found[PANELS + " > .sets__panel"], "grid-area: 1 / 1; margin-block-start: 0;")
        # the hidden card keeps its room but is not shown, read or focused;
        # it has to beat [hidden] { display: none !important }
        self.assertEqual(found[PANELS + " > .sets__panel[hidden]"],
                         "display: block !important; visibility: hidden;")

    def test_print_shows_every_card_one_after_another(self):
        blocks = media_blocks(self.print, "print")
        self.assertEqual(len(blocks), 1)
        # section 8 is print rules only
        self.assertEqual(re.sub(r"@media print\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}", "", self.print).strip(), "")
        found = rules(blocks[0])
        self.assertEqual(found[".sets__tabs"], "display: none;")
        self.assertEqual(found[PANELS], "display: block; margin-block-start: 0;")
        self.assertEqual(found[PANELS + " > .sets__panel[hidden]"], "visibility: visible;")
        self.assertEqual(found[PANELS + " > .sets__panel + .sets__panel"],
                         "margin-block-start: var(--space-lg);")

    def test_the_tab_width_is_a_menu_token(self):
        self.assertIn("var(--sets-tab-min)", self.components)
        self.assertNotIn("--events-tab-min", self.components)
        self.assertNotIn("--events-count", self.code)


class MenuStylesTest(unittest.TestCase):
    """The components of the menu (section 5), the page (5a) and its print (8)."""

    @classmethod
    def setUpClass(cls):
        raw = APP_CSS.read_text(encoding="utf-8")
        sections = section_texts(raw)
        cls.components = rules(strip_comments(sections["5"][1]))
        cls.page_code = strip_comments(sections["5a"][1])
        cls.page = rules(cls.page_code)
        cls.print = rules(media_blocks(strip_comments(sections["8"][1]), "print")[0])

    def test_the_components_are_in_section_5(self):
        for selector in (".note-line", ".pills", ".pill", ".pill--flag", ".pill--plain",
                         ".legend", ".legend__mark", ".seat-table", ".seat-number",
                         ".seat-number--couple", ".seating__meta", ".text-widget--card",
                         ".text-widget--signature", ".dishes", ".dish", ".drink",
                         ".schedule--ruled .schedule__item", ".staff-bar", ".staff-footer",
                         ".sets__head", ".sets__pairing, .sets__swaps", ".sets__note"):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.components)

    def test_the_page_is_in_section_5a(self):
        for selector in (".cover", ".cover--staff", ".cover__counters", ".menu--staff body"):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.page)
        # the page depends on the audience alone, never on the width
        self.assertNotRegex(self.page_code, r"@media|@container")

    def test_the_flags_use_the_menu_tokens(self):
        self.assertEqual(self.components[".pill--flag"],
                         "border-color: var(--color-flag-line); "
                         "background-color: var(--color-flag-bg); "
                         "color: var(--color-flag-text); "
                         "font-weight: var(--font-weight-heading);")
        mark = self.components[".legend__mark"]
        self.assertIn("background-color: var(--color-flag);", mark)
        self.assertIn("color: var(--color-on-flag);", mark)
        self.assertIn("border-radius: var(--radius-round);", mark)

    def test_an_empty_row_of_pills_takes_no_room(self):
        self.assertEqual(self.components[".pills:empty"], "display: none;")

    def test_the_courses_are_numbered_by_a_counter_of_the_list(self):
        self.assertIn("counter-reset: course;", self.components[".sets__courses"])
        self.assertIn("counter-increment: course;", self.components[".sets__courses > .dish"])
        self.assertIn("content: counter(course);", self.components[".sets__courses > .dish::before"])

    def test_the_audience_sets_the_alignment_and_the_type_size(self):
        self.assertEqual(self.page[".menu--guest .cover, .menu--guest .section"],
                         "text-align: center;")
        self.assertEqual(self.page[".menu--guest .card, .menu--guest .text-widget--card"],
                         "text-align: start;")
        # one step of the body text larger: 17px at a 16px root
        self.assertEqual(self.page[".menu--staff body"],
                         "font-size: calc(var(--text-base) * var(--text-base-desktop) "
                         "/ var(--text-base-mobile));")

    def test_print_keeps_the_background_colours_of_flags_and_labels(self):
        self.assertEqual(self.print[".legend__mark, .pill, .time-label--strong, .staff-bar"],
                         "-webkit-print-color-adjust: exact; print-color-adjust: exact;")

    def test_print_of_the_staff_page_is_compact(self):
        self.assertEqual(self.print[".menu--staff .section"], "margin-block: var(--space-md);")
        self.assertEqual(self.print[".seat-table td"],
                         "padding-block: calc(var(--space-3xs) / 2);")
        self.assertEqual(self.print[".seat-number"], "padding-block: 0;")
        self.assertEqual(self.print[".seat-table tr"], "break-inside: avoid;")
        self.assertEqual(self.print[".sets__panel"], "break-inside: avoid;")


if __name__ == "__main__":
    unittest.main()
