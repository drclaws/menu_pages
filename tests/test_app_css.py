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


if __name__ == "__main__":
    unittest.main()
