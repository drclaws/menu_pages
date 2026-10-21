"""The page template and the fragments against the contract of the page tree.

The trees are written by hand (`tests/page_trees.py`).  Every node is wrapped
in a `Strict` dict, which fails when a fragment asks for a field that its kind
of node does not have, even inside an `if:`, and which records every field a
fragment asks for: a field of the contract that no fragment reads has to be
listed in `UNREAD` with its reason.  The pages are rendered the way the build
publishes them (the comments removed) and go through the checks of the finished
HTML of the invitations builder.
"""

from __future__ import annotations

import collections
import copy
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from menu_tools import _core as core  # noqa: E402  (imported after sys.path is prepared)
from tests import page_trees as T  # noqa: E402

TEMPLATE = ROOT / "template.html"
FRAGMENTS_DIR = ROOT / "fragments"
APP_JS = ROOT / "assets" / "app.js"

#: The files of the output a page refers to.
PUBLISHED = frozenset({"assets/app.css", "assets/app.js", "assets/favicon.svg"})
#: The invitations live next to the menu; the link back leads there.
ALLOW_PATHS = ("/i",)

#: The partials: the shared pieces that no value of the data can choose.
PARTIALS = ("dish-item", "legend", "pills", "scheme", "seat-table", "section-head",
            "section-note", "sections")

SCHEME_REASON = "the scheme partial prints no markup, so no field of the scheme is read"

#: The fields of the contract that no fragment reads, with the reason.
UNREAD = {
    "section.id": "the id of the data; the page names a section by its domId",
    "set.id": "the id of the data; the page names a set by its domId",
    "sets.count": "the script counts the tabs itself; multiple tells whether there are tabs",
    "seating.mySeats": "the page shows the own seats by seatLabel and on the scheme",
    "mySeat.number": "a field of mySeats",
    "mySeat.mark": "a field of mySeats",
    **{f"{kind}.{field}": SCHEME_REASON
       for kind in ("scheme", "schemeCouple", "schemeSeat", "schemeBadge", "schemeLabel")
       for field in T.NODES[kind]},
}

#: The fields that only the staff page fills: a guest's page has them empty
#: and never reads them.
STAFF_ONLY = frozenset({
    "root.staff", "staff.updated", "staff.contact", "staff.reminder",
    "root.counters", *(f"counters.{field}" for field in T.NODES["counters"]),
    "seating.legend", "seating.rows", "seating.footnote",
    *(f"legend.{field}" for field in T.NODES["legend"]),
    *(f"row.{field}" for field in T.NODES["row"]),
    "dish.allergens", "dish.tags", "dish.noRestrictions", "dish.swapLines", "dish.note",
    "set.swapLines", "drinks.list",
})
#: The fields that only a guest's page fills: the staff page has them empty
#: (or has no such widget) and never reads them.
GUEST_ONLY = frozenset({
    "seating.mySeats", *(f"mySeat.{field}" for field in T.NODES["mySeat"]),
    "seating.seatLabel", "seating.whoLabel",
    "drinks.groups", *(f"group.{field}" for field in T.NODES["group"]),
    *(f"link.{field}" for field in T.NODES["widget:link"] if field not in T.WIDGET_COMMON_FIELDS),
})

#: The words of the interface: they live in the fragments, never in the tree.
STAFF_WORDS = ("Staff version · not for guests", "updated", "No.", "Guest · dietary notes",
               "’s guest", "[name]", "no restrictions", "Contact on the night:")
#: The classes of the parts that the staff page alone has.
STAFF_CLASSES = ("staff-bar", "staff-footer", "cover--staff", "cover__counters", "legend",
                 "seat-table", "seat-number", "pills", "pill", "dish__line", "sets__swaps",
                 "drinks__staff", "seating__footnote", "seating__divider")


def field_name(kind: str, field: str) -> str:
    """`<kind>.<field>`; the fields every widget has are `widget.<field>`."""
    if kind.startswith("widget:"):
        return f"widget.{field}" if field in T.WIDGET_COMMON_FIELDS else f"{kind[7:]}.{field}"
    return f"{kind}.{field}"


#: Every field of the contract, by its name.
CONTRACT = frozenset(field_name(kind, field) for kind, fields in T.NODES.items()
                     for field in fields)


class Strict(dict):
    """A node of the page tree that fails on a field outside its kind.

    The template engine looks a field up with `in` before it takes the value,
    so `__contains__` sees every field a fragment asks for and records it.
    """

    def __init__(self, kind: str, values: dict, reads: set[str]):
        super().__init__(values)
        self.kind = kind
        self.reads = reads

    def __contains__(self, key: object) -> bool:
        if not dict.__contains__(self, key):
            raise AssertionError(f"a fragment reads the field {key!r}, "
                                 f"which a {self.kind} node lacks")
        self.reads.add(field_name(self.kind, str(key)))
        return True


def strict(tree: dict, reads: set[str], kind: str = "root") -> Strict:
    """`tree` with every node a `Strict` dict that records into `reads`."""
    kind = T.node_kind(kind, tree)
    values = {}
    for field, value in tree.items():
        child = T.CHILDREN.get((kind, field))
        if child is not None and isinstance(value, list):
            value = [strict(item, reads, child) for item in value]
        elif child is not None and isinstance(value, dict):
            value = strict(value, reads, child)
        values[field] = value
    return Strict(kind, values, reads)


def render_page(tree: dict, template: core.Template | None = None) -> str:
    """The finished page: rendered, comments removed, as the build publishes it."""
    template = template or core.load_template(TEMPLATE)
    return core.strip_html_comments(template.render(tree), TEMPLATE.name)


def render_strict(tree: dict, template: core.Template, reads: set[str] | None = None) -> str:
    """The page of `tree` with every node `Strict`: a variant of a tree reaches
    branches the four trees do not, and a field outside the contract read
    there fails as well."""
    return render_page(strict(tree, set() if reads is None else reads), template)


def html_problems(page: str) -> list[tuple[int, str]]:
    return core.check_html(page, PUBLISHED.__contains__, allow_paths=ALLOW_PATHS)


def sections_of(tree: dict, section_id: str) -> dict:
    return next(section for section in tree["sections"] if section["id"] == section_id)


def widgets_of(tree: dict, kind: str) -> list[dict]:
    return [widget for section in tree["sections"] for widget in section["widgets"]
            if widget["type"] == kind]


def element(page: str, class_name: str) -> str:
    """The first element with the class, from its start tag to the matching end tag."""
    start = re.search(r'<(\w+)\b[^>]*\sclass="(?:[^"]* )?%s(?: [^"]*)?"' % re.escape(class_name),
                      page)
    assert start, class_name
    tag, depth, position = start.group(1), 0, start.start()
    for match in re.finditer(r"<(/?)%s\b[^>]*>" % tag, page[position:]):
        depth += -1 if match.group(1) else 1
        if depth == 0:
            return page[position:position + match.end()]
    raise AssertionError(f"no end of {class_name}")


def visible_text(markup: str) -> str:
    """The text of the markup, tags dropped and white space collapsed."""
    text = re.sub(r"<[^>]+>", " ", markup)
    for entity, char in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')):
        text = text.replace(entity, char)
    return " ".join(text.split())


class Outline(HTMLParser):
    """Ids, references, headings, hidden elements and reveal marks of a page."""

    VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
                      "meta", "source", "track", "wbr"})

    def __init__(self, document: str):
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.headings: list[int] = []
        self.hidden: list[tuple[str, dict]] = []
        self.reveals: list[tuple[str, dict]] = []
        self.nested_reveals = 0
        self.scripts: list[dict] = []
        self.styles: list[str] = []
        self.open: list[tuple[str, bool]] = []
        self.feed(document)
        self.close()

    def element(self, tag: str, attrs: list[tuple[str, str | None]], void: bool) -> None:
        attributes = {name: value or "" for name, value in attrs}
        if "id" in attributes:
            self.ids.append(attributes["id"])
        for name in ("aria-labelledby", "aria-controls", "aria-describedby"):
            for target in attributes.get(name, "").split():
                self.references.append((name, target))
        if attributes.get("href", "").startswith("#"):
            self.references.append(("href", attributes["href"][1:]))
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        if "hidden" in attributes:
            self.hidden.append((tag, attributes))
        if tag == "script":
            self.scripts.append(attributes)
        self.styles += [name for name in attributes if name == "style" or name.startswith("on")]
        reveal = "data-reveal" in attributes
        if reveal:
            self.reveals.append((tag, attributes))
            if any(marked for _tag, marked in self.open):
                self.nested_reveals += 1
        if not void:
            self.open.append((tag, reveal))

    def handle_starttag(self, tag, attrs):
        self.element(tag, attrs, tag in self.VOID)

    def handle_startendtag(self, tag, attrs):
        self.element(tag, attrs, True)

    def handle_endtag(self, tag):
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index][0] == tag:
                del self.open[index:]
                break


def tabs_hooks() -> list[str]:
    """The data attributes the tabs module of the script looks for."""
    source = APP_JS.read_text(encoding="utf-8")
    module = source[source.index("Module tabs"):source.index("Module reveal")]
    hooks = re.findall(r"'\[(data-[a-z-]+)\]'", module)
    assert hooks, "no hooks in the tabs module"
    return sorted(set(hooks))


# --- the trees and the files ---------------------------------------------------

class TreeTests(unittest.TestCase):
    def test_every_node_has_exactly_the_fields_of_its_kind(self):
        seen = set()
        for name, tree in T.all_trees().items():
            for kind, value in T.nodes(tree):
                seen.add(kind)
                with self.subTest(tree=name, node=kind):
                    self.assertEqual(list(value), list(T.NODES[kind]))
        # every kind of node is in a tree, except the scheme: it is null in all
        scheme_kinds = {"scheme", "schemeCouple", "schemeSeat", "schemeBadge", "schemeLabel"}
        self.assertEqual(seen, set(T.NODES) - scheme_kinds)
        # the guest's scheme has the labels, the staff scheme the badges
        kinds = set()
        for staff_page in (False, True):
            for kind, value in T.nodes(T.scheme_example(staff_page), "scheme"):
                kinds.add(kind)
                self.assertEqual(list(value), list(T.NODES[kind]))
        self.assertEqual(kinds, scheme_kinds)

    def test_a_node_outside_the_contract_is_refused(self):
        with self.assertRaises(ValueError):
            T.node("drink", category="Red", name="Example Red")
        with self.assertRaises(ValueError):
            T.node("drink", category="Red", name="Example Red", line="", price="")

    def test_the_trees_cover_the_cases(self):
        trees = T.all_trees()
        plus_one = widgets_of(trees["guest-plus-one"], "seating")[0]
        self.assertEqual([(seat["number"], seat["mark"]) for seat in plus_one["mySeats"]],
                         [(8, "You"), (9, "+1")])
        self.assertIsNone(plus_one["scheme"])
        alone = widgets_of(trees["guest-without-table"], "seating")[0]
        self.assertEqual((alone["seatLabel"], alone["scheme"]), ("Seat 1", None))
        pair = widgets_of(trees["guest-pair"], "seating")[0]
        self.assertEqual(pair["whoLabel"], "Peggy and Victor")
        self.assertEqual(len(widgets_of(trees["guest-pair"], "sets")[0]["items"]), 1)
        rows = widgets_of(trees["staff"], "seating")[0]["rows"]
        self.assertEqual(len([row for row in rows if row["isFree"]]), 2)
        self.assertEqual(len([row for row in rows if row["isCouple"]]), 2)
        self.assertEqual(sorted(row["name"] for row in rows if row["isPlusOne"]), ["", "Oscar"])
        self.assertTrue(widgets_of(trees["staff"], "seating")[0]["legend"])
        titles = [widget["title"] for widget in widgets_of(trees["staff"], "dishes")]
        self.assertEqual(titles, ["", "On request"])
        # the title of a list is for both audiences
        titles = [widget["title"] for widget in widgets_of(trees["guest-without-table"], "dishes")]
        self.assertEqual(titles, ["For the table"])
        self.assertTrue(widgets_of(trees["guest-plus-one"], "drinks")[0]["note"])
        self.assertTrue(widgets_of(trees["staff"], "drinks")[0]["note"])
        self.assertTrue(widgets_of(trees["staff"], "sets")[0]["note"])
        variants = {widget["variant"] for tree in trees.values()
                    for widget in widgets_of(tree, "text")}
        self.assertEqual(variants, set(T.ENUMS["variant"]))
        layouts = {group["layout"] for tree in trees.values()
                   for widget in widgets_of(tree, "drinks") for group in widget["groups"]}
        self.assertEqual(layouts, set(T.ENUMS["layout"]))

    def test_the_staff_page_has_its_texts_and_counters(self):
        for name, tree in T.all_trees().items():
            with self.subTest(tree=name):
                self.assertEqual(name == "staff", tree["isStaff"])
        staff = T.staff()
        self.assertTrue(all(staff["staff"].values()))
        self.assertTrue(all(staff["counters"].values()))

    def test_the_fields_of_the_other_audience_are_empty(self):
        def empty(value) -> bool:
            if isinstance(value, dict):
                return all(empty(item) for item in value.values())
            return not value

        for name, tree in T.all_trees().items():
            other = GUEST_ONLY if tree["isStaff"] else STAFF_ONLY
            for kind, value in T.nodes(tree):
                for field, item in value.items():
                    if field_name(kind, field) in other:
                        with self.subTest(tree=name, field=field_name(kind, field)):
                            self.assertTrue(empty(item))


class FragmentFilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {path.relative_to(FRAGMENTS_DIR).with_suffix("").as_posix():
                       path.read_text(encoding="utf-8")
                       for path in sorted(FRAGMENTS_DIR.rglob("*.html"))}

    def test_the_files_are_the_types_and_the_partials(self):
        fragments = core.load_fragments(FRAGMENTS_DIR)
        self.assertEqual(fragments.names("sections"), sorted(T.SECTION_TYPES))
        self.assertEqual(fragments.names("widgets"), sorted(T.WIDGET_TYPES))
        self.assertEqual(fragments.names("partials"), sorted(PARTIALS))
        self.assertEqual(len(fragments), len(T.SECTION_TYPES) + len(T.WIDGET_TYPES)
                         + len(PARTIALS))

    def test_every_fragment_starts_with_its_contract(self):
        for name, source in self.sources.items():
            with self.subTest(fragment=name):
                self.assertTrue(source.startswith("<!-- "), "no contract comment")
                self.assertIn("expects in ", source[:source.index("-->")])

    def test_the_contract_comments_name_only_fields_of_the_contract(self):
        # every name in camel case is a field (the plain words may be prose)
        fields = {field for names in T.NODES.values() for field in names}
        named = set()
        for name, source in self.sources.items():
            comment = source[:source.index("-->")]
            listed = comment[comment.index("expects in "):].split(". ", 1)[0]
            for word in re.findall(r"\b[a-z]+[A-Z][A-Za-z]*\b", listed):
                named.add(word)
                with self.subTest(fragment=name, field=word):
                    self.assertIn(word, fields)
        self.assertLessEqual({"domId", "titleId", "isStaff", "seatLabel", "swapLines"}, named)

    def test_class_modifiers_come_only_from_checked_enumerations(self):
        for name, source in self.sources.items():
            for classes in re.findall(r'class="([^"]*)"', source):
                for field in re.findall(r"\{\{\s*([^}]*?)\s*\}\}", classes):
                    with self.subTest(fragment=name, field=field):
                        self.assertTrue(field.startswith("."), field)
                        self.assertIn(field[1:], T.ENUMS)

    def test_ids_are_dom_ids_of_the_tree_with_fixed_suffixes(self):
        for name, source in self.sources.items():
            for value in re.findall(r'\sid="([^"]*)"', source):
                with self.subTest(fragment=name, id=value):
                    self.assertRegex(value, r"^\{\{\.(domId|titleId)\}\}(--title|--tab)?$")

    def test_the_reveal_mark_is_in_the_frame_of_a_section_on_the_guest_page_only(self):
        marked = {name: source.count("data-reveal") for name, source in self.sources.items()
                  if "data-reveal" in source}
        self.assertEqual(marked, {"sections/custom": 1})
        self.assertIn('<!-- if:!isStaff --><div class="container" data-reveal><!-- endif -->'
                      '<!-- if:isStaff --><div class="container"><!-- endif -->',
                      self.sources["sections/custom"])
        self.assertNotIn("data-reveal", TEMPLATE.read_text(encoding="utf-8"))

    def test_no_styles_or_inline_scripts_in_the_markup(self):
        sources = dict(self.sources, template=TEMPLATE.read_text(encoding="utf-8"))
        for name, source in sources.items():
            markup = re.sub(r"<!--.*?-->", "", source, flags=re.S)
            with self.subTest(file=name):
                self.assertNotRegex(markup, r"<[a-zA-Z][^>]*\sstyle\s*=")
                self.assertNotRegex(markup, r"(?i)<style[\s>]")
                self.assertNotRegex(markup, r"<[a-zA-Z][^>]*\son[a-z]+\s*=")
                scripts = re.findall(r"(?i)<script\b[^>]*>.*?</script>", markup, re.S)
                expected = ['<script src="{{assetsPath}}/app.js" defer></script>'] \
                    if name == "template" else []
                self.assertEqual(scripts, expected)

    def test_the_words_of_the_interface_are_in_the_fragments(self):
        markup = "".join(re.sub(r"<!--.*?-->", "", source, flags=re.S)
                         for source in self.sources.values())
        markup += TEMPLATE.read_text(encoding="utf-8")
        for word in STAFF_WORDS + ("Paired with", "—", "Dinner menu · "):
            with self.subTest(word=word):
                self.assertIn(word, markup)

    def test_the_scheme_partial_prints_nothing(self):
        source = self.sources["partials/scheme"]
        self.assertEqual(source.count("<!--"), 1)
        self.assertTrue(source.rstrip().endswith("-->"))
        for staff_page in (False, True):
            frame = "<!-- with:scheme --><!-- include:partials/scheme --><!-- endwith -->"
            template = core.parse_template(frame, "frame", core.load_fragments(FRAGMENTS_DIR))
            reads: set[str] = set()
            scheme = strict(T.scheme_example(staff_page), reads, "scheme")
            output = core.strip_html_comments(template.render({"scheme": scheme}), "frame")
            self.assertEqual(output.strip(), "")
            self.assertEqual(reads, set())


# --- the contract ---------------------------------------------------------------

class ContractTests(unittest.TestCase):
    """Every field a fragment reads is in the contract; every one is read."""

    @classmethod
    def setUpClass(cls):
        cls.template = core.load_template(TEMPLATE)
        cls.page_reads: dict[str, set[str]] = {name: set() for name in T.TREES}
        cls.pages = {name: render_page(strict(tree, cls.page_reads[name]), cls.template)
                     for name, tree in T.all_trees().items()}
        cls.reads = set().union(*cls.page_reads.values())

    def test_the_trees_render(self):
        self.assertEqual(set(self.pages), set(T.TREES))
        for name, page in self.pages.items():
            with self.subTest(tree=name):
                self.assertTrue(page.startswith("<!doctype html>\n<html lang=\"en\""))

    def test_a_field_outside_the_contract_fails(self):
        for build, kind, field in ((T.guest_plus_one, "section", "eyebrow"),
                                   (T.guest_plus_one, "dish", "ingredients"),
                                   (T.guest_plus_one, "set", "hint"),
                                   (T.staff, "row", "isFree"),
                                   (T.staff, "dish", "swapLines"),
                                   (T.staff, "root", "counters")):
            tree = build()
            victims = [value for node_kind, value in T.nodes(tree) if node_kind == kind]
            del victims[-1][field]
            with self.subTest(kind=kind, field=field), self.assertRaises(AssertionError):
                render_page(strict(tree, set()), self.template)

    def test_every_field_of_the_contract_is_read_or_listed(self):
        self.assertLessEqual(set(UNREAD), CONTRACT)
        self.assertLessEqual(self.reads, CONTRACT)
        self.assertEqual(self.reads & set(UNREAD), set())
        self.assertEqual(CONTRACT - self.reads, set(UNREAD))
        for field, reason in UNREAD.items():
            with self.subTest(field=field):
                self.assertTrue(reason)

    def test_each_page_reads_the_fields_of_its_audience_only(self):
        # a staff field read on a guest's page would show the staff part as
        # soon as the data layer filled it there by mistake, and the other way
        self.assertLessEqual(STAFF_ONLY | GUEST_ONLY, CONTRACT)
        self.assertEqual(STAFF_ONLY & GUEST_ONLY, frozenset())
        for name, reads in self.page_reads.items():
            other = GUEST_ONLY if name == "staff" else STAFF_ONLY
            with self.subTest(page=name):
                self.assertEqual(reads & other, set())
        # and each page does read the fields of its own audience
        self.assertLessEqual(STAFF_ONLY, self.page_reads["staff"])
        guests = set().union(*(reads for name, reads in self.page_reads.items()
                               if name != "staff"))
        self.assertEqual(GUEST_ONLY - guests, GUEST_ONLY & set(UNREAD))


# --- the pages --------------------------------------------------------------------

class PageTests(unittest.TestCase):
    """The pages of the hand-made trees, as the build would publish them."""

    @classmethod
    def setUpClass(cls):
        cls.template = core.load_template(TEMPLATE)
        cls.trees = T.all_trees()
        cls.pages = {name: render_strict(tree, cls.template) for name, tree in cls.trees.items()}

    def guest_pages(self):
        return {name: page for name, page in self.pages.items() if name != "staff"}

    def test_the_pages_pass_the_checks_of_the_build(self):
        for name, page in self.pages.items():
            with self.subTest(page=name):
                core.check_rendered(page)
                self.assertEqual(html_problems(page), [])

    def test_no_styles_and_no_inline_scripts(self):
        for name, page in self.pages.items():
            outline = Outline(page)
            with self.subTest(page=name):
                self.assertEqual(outline.styles, [])
                self.assertNotRegex(page, r"(?i)<style[\s>]")
                self.assertEqual(outline.scripts, [{"src": "/assets/app.js", "defer": ""}])
                self.assertRegex(page, r'<script src="/assets/app.js" defer></script>')

    def test_ids_are_unique_and_every_reference_resolves(self):
        for name, page in self.pages.items():
            outline = Outline(page)
            with self.subTest(page=name):
                repeated = [value for value, count in collections.Counter(outline.ids).items()
                            if count > 1]
                self.assertEqual(repeated, [])
                self.assertTrue(all(outline.ids))
                dangling = [(attribute, target) for attribute, target in outline.references
                            if target not in outline.ids]
                self.assertEqual(dangling, [])

    def test_the_heading_outline_has_no_gaps(self):
        for name, page in self.pages.items():
            levels = Outline(page).headings
            with self.subTest(page=name, levels=levels):
                self.assertEqual(levels[0], 1)
                self.assertEqual(levels.count(1), 1)
                for previous, level in zip(levels, levels[1:]):
                    self.assertLessEqual(level, previous + 1)
                self.assertIn(3, levels)  # the sets

    def test_the_reveal_mark_is_on_the_guest_page_alone(self):
        for name, page in self.pages.items():
            outline = Outline(page)
            custom = [section for section in self.trees[name]["sections"]
                      if section["type"] == "custom"]
            with self.subTest(page=name):
                if name == "staff":
                    self.assertEqual(outline.reveals, [])
                    continue
                self.assertEqual(len(outline.reveals), len(custom))
                self.assertEqual(outline.nested_reveals, 0)
                for tag, attributes in outline.reveals:
                    self.assertEqual((tag, attributes["class"]), ("div", "container"))

    def test_everything_is_visible_without_the_script(self):
        for name, page in self.pages.items():
            hidden = Outline(page).hidden
            with self.subTest(page=name):
                for _tag, attributes in hidden:
                    self.assertIn("data-tabs-tablist", attributes)

    def test_the_head_of_the_page(self):
        for name, page in self.pages.items():
            head = page[:page.index("</head>")]
            audience = "staff" if name == "staff" else "guest"
            with self.subTest(page=name):
                self.assertTrue(page.startswith(
                    f'<!doctype html>\n<html lang="en" class="menu menu--{audience}">\n<head>'))
                for tag in ('<meta charset="utf-8">',
                            '<meta name="viewport" content="width=device-width, initial-scale=1, '
                            'viewport-fit=cover">',
                            '<meta name="color-scheme" content="only light">',
                            '<meta name="theme-color" content="#f1f2f4">',
                            '<meta name="text-scale" content="scale">',
                            '<meta name="referrer" content="no-referrer">',
                            '<meta name="robots" content="noindex, nofollow">',
                            "<title>Dinner menu · Ivan &amp; Vera</title>",
                            '<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">',
                            '<link rel="stylesheet" href="/assets/app.css">'):
                    self.assertIn(tag, head)
                # no link preview: no Open Graph, no cards, no description
                self.assertNotRegex(head, r'property="og:|name="twitter:|name="description"')
                self.assertEqual(page.count("<html"), 1)

    def test_the_staff_bar_and_footer(self):
        page = self.pages["staff"]
        bar = element(page, "staff-bar")
        self.assertTrue(page.index("<body>") < page.index(bar) < page.index("<main"))
        self.assertEqual(visible_text(bar), "Staff version · not for guests updated 10 June 2030")
        footer = element(page, "page-footer")
        self.assertGreater(page.index(footer), page.index("</main>"))
        self.assertEqual(
            re.findall(r"<p[^>]*>(.*?)</p>", footer),
            ["Contact on the night: Selma (planner) · +00 000 000 00 00",
             "Staff link only — please do not show this page to guests.",
             "Print it on the morning of the dinner."])
        self.assertNotIn("<a ", footer)  # the phone is text, not a link

    def test_the_staff_frame_without_some_of_its_texts(self):
        def page(**staff):
            tree = T.staff()
            tree["staff"].update(staff)
            reads: set[str] = set()
            document = render_strict(tree, self.template, reads)
            self.assertEqual(reads & GUEST_ONLY, set())
            self.assertEqual(html_problems(document), [])
            return document

        no_contact = page(contact="")
        self.assertNotIn("Contact on the night", no_contact)
        self.assertIn("Print it on the morning of the dinner.", element(no_contact, "page-footer"))
        nothing = page(contact="", reminder="")
        self.assertNotIn("page-footer", nothing)
        self.assertNotIn("staff-footer", nothing)
        no_reminder = page(reminder="")
        self.assertEqual(len(re.findall(r"<p", element(no_reminder, "staff-footer"))), 1)
        undated = page(updated="")
        self.assertEqual(visible_text(element(undated, "staff-bar")),
                         "Staff version · not for guests")

    def test_a_guest_page_has_no_staff_parts(self):
        for name, page in self.guest_pages().items():
            classes = {value for found in re.findall(r'class="([^"]*)"', page)
                       for value in found.split()}
            with self.subTest(page=name):
                self.assertEqual(classes & set(STAFF_CLASSES), set())
                for word in STAFF_WORDS:
                    self.assertNotIn(word, visible_text(page))
                self.assertNotIn("<table", page)
                self.assertNotIn("<footer", page)

    def test_the_modifiers_are_the_enumerations(self):
        everything = "".join(self.pages.values())
        for variant in T.ENUMS["variant"]:
            self.assertIn(f"text-widget--{variant}", everything)
        for layout in T.ENUMS["layout"]:
            self.assertIn(f"drinks__group--{layout}", everything)

    def test_values_are_escaped(self):
        tree = T.guest_plus_one()
        widgets_of(tree, "seating")[0]["whoLabel"] = "Olga <b>& co</b> {{x}}"
        widgets_of(tree, "dishes")[0]["items"][0]["name"] = "<script>alert(1)</script>"
        page = render_strict(tree, self.template)
        self.assertIn("Olga &lt;b&gt;&amp; co&lt;/b&gt; &#123;&#123;x&#125;&#125;", page)
        self.assertNotIn("<b>", page)
        self.assertNotIn("<script>alert", page)
        core.check_rendered(page)
        self.assertEqual(html_problems(page), [])


class WidgetTests(unittest.TestCase):
    """What each section and widget shows to the guest and to the staff."""

    @classmethod
    def setUpClass(cls):
        cls.template = core.load_template(TEMPLATE)
        cls.pages = {name: render_strict(tree, cls.template)
                     for name, tree in T.all_trees().items()}

    def section(self, page: str, section_id: str) -> str:
        found = re.search(r'<section class="[^"]*" id="s-%s".*?</section>' % section_id,
                          self.pages[page], re.S)
        self.assertIsNotNone(found, section_id)
        return found.group(0)

    def test_the_cover_of_a_guest(self):
        cover = self.section("guest-plus-one", "cover")
        self.assertIn('<p class="section__subtitle cover__eyebrow">Ivan &amp; Vera</p>', cover)
        self.assertIn('<h1 class="cover__title" id="s-cover--title">Wedding dinner</h1>', cover)
        self.assertIn('<hr class="divider divider--accent cover__divider">', cover)
        self.assertIn('<p class="cover__when">15 June 2030, 19:00</p>', cover)
        self.assertIn('<p class="cover__place">Riverside Bistro · Example Street 5</p>', cover)
        self.assertNotIn("cover--staff", cover)

    def test_the_header_of_the_staff_page(self):
        cover = self.section("staff", "cover")
        self.assertIn('<section class="cover cover--staff" id="s-cover"', cover)
        self.assertIn(">Ivan &amp; Vera · Wedding dinner</p>", cover)
        self.assertIn('<h1 class="cover__title" id="s-cover--title">15 June 2030, 19:00</h1>',
                      cover)
        self.assertEqual(re.findall(r'<li class="(pill[^"]*)">([^<]*)</li>', cover),
                         [("pill pill--plain", "14 guests"),
                          ("pill pill--plain", "L-shaped table"),
                          ("pill pill--flag", "5 dietary notes")])
        self.assertNotIn("divider", cover)

    def test_the_counters_show_only_what_there_is(self):
        tree = T.staff()
        tree["counters"].update(notes=0, notesText="", tableLabel="")
        cover = re.search(r'<section class="cover.*?</section>',
                          render_strict(tree, self.template), re.S).group(0)
        self.assertEqual(re.findall(r'<li class="pill[^"]*">([^<]*)</li>', cover), ["14 guests"])

    def test_the_seats_of_a_guest(self):
        cases = {"guest-plus-one": ("Seats 8 &amp; 9", "Olga and your guest"),
                 "guest-without-table": ("Seat 1", "Klara"),
                 "guest-pair": ("Seats 12 &amp; 13", "Peggy and Victor")}
        for name, (seats, who) in cases.items():
            section = self.section(name, "seats")
            with self.subTest(page=name):
                self.assertIn(
                    f'<p class="seating__meta"><span class="time-label time-label--strong '
                    f'seating__seats">{seats}</span> <span class="seating__who">{who}</span></p>',
                    section)
                self.assertIn('<div class="card seating__card">', section)
                for part in ("legend", "seat-table", "seating__footnote", "<hr"):
                    self.assertNotIn(part, section)

    def test_the_legend_and_the_seat_table(self):
        section = self.section("staff", "seats")
        legend = element(section, "legend")
        self.assertEqual(re.findall(r'<span class="legend__mark" aria-hidden="true">(\w)</span>'
                                    r'<span class="legend__label">([^<]*)</span>', legend),
                         list(T.LEGEND))
        self.assertLess(section.index(legend), section.index("seating__card"))
        table = element(section, "seat-table")
        self.assertIn('<th class="seat-table__no" scope="col">No.</th>'
                      '<th scope="col">Guest · dietary notes</th>', table)
        rows = re.findall(r"<tr>\s*<td.*?</tr>", table, re.S)
        self.assertEqual(len(rows), 16)
        text = [visible_text(row) for row in rows]
        self.assertEqual(text[0], "1 Alyona no alcohol")
        self.assertEqual(text[1], "2 —")
        self.assertEqual(text[3], "4 Vera · bride")
        self.assertEqual(text[8], "9 +1 · Olga’s guest, [name]")
        self.assertEqual(text[9], "10 Egor no gluten no lactose")
        self.assertEqual(text[10], "11 —")
        self.assertEqual(text[15], "16 +1 · Nina’s guest, Oscar")
        self.assertIn('<span class="seat-number seat-number--couple">4</span>', rows[3])
        self.assertIn('<span class="seat-number">3</span>', rows[2])
        self.assertEqual(re.findall(r'<li class="pill pill--flag">([^<]*)</li>', rows[9]),
                         ["no gluten", "no lactose"])
        self.assertNotIn("pills", rows[5])
        self.assertIn('<p class="note-line seating__footnote">Main course:', section)
        # no scheme: no rule between a scheme and the table
        self.assertNotIn("seating__divider", section)

    def test_the_seating_widget_with_a_scheme_object(self):
        for name in ("guest-plus-one", "staff"):
            tree = T.all_trees()[name]
            widgets_of(tree, "seating")[0]["scheme"] = T.scheme_example(name == "staff")
            page = render_strict(tree, self.template)
            with self.subTest(page=name):
                self.assertEqual(html_problems(page), [])
                self.assertEqual("seating__divider" in page, name == "staff")

    def test_the_dishes_of_a_guest(self):
        section = self.section("guest-plus-one", "starters")
        items = re.findall(r'<li class="dish">(.*?)</li>', section, re.S)
        self.assertEqual(len(items), len(T.STARTERS))
        self.assertEqual(re.findall(r"<p [^>]*>([^<]*)</p>", items[0]),
                         ["Beetroot tartare", "Beetroot, walnuts, rye crisp"])
        self.assertNotIn("dishes__title", section)
        # the title of a list is not a staff part: a guest's list may have one
        titled = self.section("guest-without-table", "starters")
        self.assertRegex(titled, r'<div class="widget dishes-widget" id="s-starters--w1">\s*'
                                 r'<p class="dishes__title">For the table</p>\s*'
                                 r'<ul class="dishes" role="list">')
        self.assertNotIn("pills", titled)

    def test_the_dishes_of_the_staff(self):
        section = self.section("staff", "starters")
        lists = re.findall(r'<div class="widget dishes-widget".*?</ul>\s*</div>', section, re.S)
        self.assertEqual(len(lists), 2)
        items = re.findall(r'<li class="dish">(.*?)\n</li>', lists[0], re.S)
        self.assertEqual(len(items), len(T.STARTERS))
        self.assertEqual(visible_text(items[0]),
                         "Beetroot tartare nuts gluten Seat 3 — serve the nut-free version on a "
                         "separate plate Seat 10 — serve it without the rye crisp")
        self.assertIn('<li class="pill pill--flag">nuts</li><li class="pill pill--flag">gluten'
                      '</li>', items[0])
        self.assertIn('<ul class="pills" role="list"><li class="pill">vegan · gluten-free</li>'
                      '</ul>', items[2])
        self.assertIn('<p class="note-line dish__line">Keep the dill sauce on the side</p>',
                      items[3])
        self.assertIn('<li class="pill">no restrictions</li>', items[4])
        self.assertNotIn("dish__ingredients", section)
        self.assertIn('<p class="dishes__title">On request</p>', lists[1])
        self.assertIn("Mushroom risotto", lists[1])

    def test_a_dish_without_allergen_information(self):
        tree = T.staff()
        widgets_of(tree, "dishes")[0]["items"][0].update(allergens=[], swapLines=[])
        page = render_strict(tree, self.template)
        # an empty row, which the style sheet hides (.pills:empty)
        self.assertRegex(page, r'<p class="dish__name">Beetroot tartare</p>\s*'
                               r'<ul class="pills" role="list"></ul>\s*</li>')

    def test_the_sets_carry_the_hooks_of_the_script(self):
        hooks = tabs_hooks()
        self.assertEqual(hooks, ["data-tabs", "data-tabs-panel", "data-tabs-tab",
                                 "data-tabs-tablist"])
        for name in ("guest-plus-one", "guest-without-table", "staff"):
            widget = element(self.pages[name], "sets-widget")
            with self.subTest(page=name):
                for hook in hooks:
                    self.assertIn(hook, widget)
                self.assertRegex(widget, r'^<div class="widget sets-widget sets" id="[\w-]+" '
                                         r'data-tabs>')
                tablist = re.search(r"<div [^>]*data-tabs-tablist[^>]*>", widget).group(0)
                self.assertIn(' role="tablist" aria-labelledby="s-main--title"', tablist)
                self.assertTrue(tablist.endswith(" hidden>"))
                tabs = re.findall(r"<button [^>]*data-tabs-tab>", widget)
                panels = re.findall(r"<article [^>]*data-tabs-panel>", widget)
                self.assertEqual(len(tabs), len(panels))
                self.assertGreaterEqual(len(tabs), 2)
                for tab, panel in zip(tabs, panels):
                    panel_id = re.search(r' id="([^"]+)"', panel).group(1)
                    self.assertIn(f'id="{panel_id}--tab" aria-controls="{panel_id}"', tab)
                    self.assertIn(' role="tab" ', tab)
                    self.assertIn(' aria-selected="false" tabindex="-1" ', tab)
                    self.assertIn(f'aria-labelledby="{panel_id}--title"', panel)
                    self.assertNotIn("hidden", panel)

    def test_a_single_set_has_no_tabs(self):
        widget = element(self.pages["guest-pair"], "sets-widget")
        self.assertIn("data-tabs-panel", widget)
        for part in ("data-tabs-tablist", "data-tabs-tab", 'role="tab'):
            self.assertNotIn(part, widget)

    def test_the_card_of_a_set(self):
        guest = element(self.pages["guest-plus-one"], "sets-widget")
        panel = re.search(r"<article .*?</article>", guest, re.S).group(0)
        order = ['<h3 class="sets__title" id="s-main--w1--set-a--title">Set A</h3>',
                 '<p class="sets__eyebrow">two courses</p>', '<ol class="dishes sets__courses"',
                 "Salmon tartare", "Sea bass with a pistachio crust",
                 '<p class="note-line sets__pairing">Paired with white wine — see Wines</p>']
        positions = [panel.index(marker) for marker in order]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("sets__swaps", guest)
        self.assertTrue(guest.rstrip().endswith(
            '<p class="note-line sets__note">Your waiter will take your choice after the '
            "starters.</p>\n</div>"))
        staff = element(self.pages["staff"], "sets-widget")
        swaps = re.findall(r'<div class="sets__swaps">(.*?)</div>', staff, re.S)
        self.assertEqual(len(swaps), 2)
        self.assertEqual([visible_text(line) for line in
                          re.findall(r'<p class="note-line">([^<]*)</p>', swaps[0])],
                         list(T.SETS[0][6]))
        self.assertIn('<li class="pill pill--flag">lactose</li>', staff)
        self.assertIn("The kitchen needs every order by 20:00.", staff)

    def test_a_set_without_a_hint_an_eyebrow_or_a_pairing(self):
        widget = element(self.pages["guest-without-table"], "sets-widget")
        self.assertEqual(widget.count("sets__tab-hint"), 1 + 1)
        self.assertEqual(widget.count("sets__eyebrow"), 1)
        self.assertEqual(widget.count("sets__pairing"), 1)
        self.assertNotIn("sets__note", widget)

    def test_the_drinks_of_a_guest(self):
        widget = element(self.pages["guest-plus-one"], "drinks-widget")
        groups = re.findall(r'<div class="drinks__group drinks__group--(\w+)">(.*?)\n  </div>',
                            widget, re.S)
        self.assertEqual([layout for layout, _markup in groups], ["inline", "list"])
        self.assertEqual(visible_text(groups[0][1]), f"Soft drinks {T.SOFT_DRINKS}")
        self.assertNotIn("drinks__list", groups[0][1])
        drinks = re.findall(r'<li class="drink">(.*?)</li>', groups[1][1])
        self.assertEqual(len(drinks), 3)
        self.assertEqual(visible_text(drinks[0]), "Sparkling Example Brut, Riverside Cellars "
                                                  "Example Valley · Chardonnay · with the starters")
        self.assertNotIn("schedule", widget)
        self.assertTrue(widget.rstrip().endswith(
            '<p class="note-line drinks__note">Cocktails on request — just ask at the bar.</p>'
            "\n</div>"))
        untitled = element(self.pages["guest-without-table"], "drinks-widget")
        self.assertNotIn("drinks__title", untitled)
        self.assertNotIn("drinks__note", untitled)

    def test_the_drinks_of_the_staff(self):
        widget = element(self.pages["staff"], "drinks-widget")
        self.assertNotIn("drinks__group", widget)
        self.assertIn('<div class="schedule schedule--ruled drinks__staff">', widget)
        items = re.findall(r'<li class="schedule__item">(.*?)</li>', widget, re.S)
        self.assertEqual(len(items), 4)
        self.assertIn('<span class="time-label schedule__time">Sparkling</span>', items[0])
        self.assertIn("seat 1 — no alcohol", items[0])
        self.assertIn("Cocktails only on request; the bar has the list.", widget)

    def test_the_text_widgets_and_the_link(self):
        welcome = self.section("guest-without-table", "welcome")
        self.assertIn('<div class="widget text-widget text-widget--lead prose">', welcome)
        self.assertIn("<p>The kitchen closes at 22:00.<br>Dessert is served at the bar.</p>",
                      welcome)
        main = self.section("guest-plus-one", "main")
        self.assertIn('<div class="widget text-widget text-widget--card prose">\n  <p>Allergies',
                      main)
        signature = self.section("guest-plus-one", "signature")
        self.assertIn('<div class="widget text-widget text-widget--signature prose">\n  '
                      "<p>Ivan &amp; Vera</p>", signature)
        self.assertIn('<p class="widget link-widget"><a class="btn btn--secondary" '
                      'href="/i/heron-4tx9/">← Back to the invitation</a></p>', signature)
        self.assertIn('<div class="card section__note">', signature)
        self.assertLess(signature.index("link-widget"), signature.index("section__note"))

    def test_the_head_of_a_section(self):
        starters = self.section("guest-plus-one", "starters")
        self.assertIn('<header class="section__head">\n  <h2 class="section__title" '
                      'id="s-starters--title">Starters</h2>\n  <p class="section__subtitle">'
                      "Shared plates for the table</p>\n</header>", starters)
        seats = self.section("guest-plus-one", "seats")
        self.assertNotIn("section__subtitle", seats)
        self.assertIn('<h2 class="section__title" id="s-seats--title">Your seats</h2>', seats)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
