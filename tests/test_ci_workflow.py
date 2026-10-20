"""Static checks of the CI workflow text (no YAML parser required)."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"

ALLOWED_ACTIONS = {"actions/checkout", "actions/setup-python"}
ALLOWED_EXPRESSIONS = re.compile(
    r"^(matrix\.[\w-]+|github\.ref|github\.workflow|github\.ref != 'refs/heads/main')$")

#: The extensions of media files that must never be tracked.
MEDIA_PATTERN = r"'\.(png|jpe?g|webp|gif|avif|mp4|mov|webm|ico|svg)$'"


def strip_comments(text):
    """Drop whole-line comments and trailing ``# ...`` comments."""
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        lines.append(re.sub(r"\s+#\s.*$", "", line))
    return "\n".join(lines) + "\n"


def run_blocks(text):
    """Return the bodies of all ``run: |`` blocks."""
    blocks = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)(?:-\s+)?run:\s*(.*)$", lines[index])
        index += 1
        if not match:
            continue
        indent = len(match.group(1))
        body = [match.group(2)]
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            body.append(line)
            index += 1
        blocks.append("\n".join(body))
    return blocks


def outside_run_blocks(text):
    """Return the text without the values of the ``run:`` keys (the keys stay)."""
    kept = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)(?:-\s+)?run:", lines[index])
        index += 1
        if not match:
            kept.append(lines[index - 1])
            continue
        kept.append(match.group(0))
        indent = len(match.group(1))
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            index += 1
    return "\n".join(kept) + "\n"


def mapping_bodies(text, key, indent=None):
    """Return the non-blank body lines of every ``key:`` with nothing after the colon.

    The body is every following line indented deeper than the key; blank lines
    do not end it, as in YAML.  `indent` limits the search to keys indented by
    exactly that many spaces (0: top-level keys).
    """
    bodies = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(rf"^( *){re.escape(key)}:\s*$", line)
        if not match or (indent is not None and len(match.group(1)) != indent):
            continue
        body = []
        for following in lines[index + 1:]:
            if not following.strip():
                continue
            if len(following) - len(following.lstrip()) <= len(match.group(1)):
                break
            body.append(following)
        bodies.append(body)
    return bodies


def steps(text):
    """Return the items of every ``steps:`` block, each as its non-blank lines."""
    items = []
    for body in mapping_bodies(text, "steps"):
        item_indent = len(body[0]) - len(body[0].lstrip()) if body else 0
        for line in body:
            if len(line) - len(line.lstrip()) <= item_indent or not items:
                items.append([line])
            else:
                items[-1].append(line)
    return items


class CiWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = CI.read_text(encoding="utf-8")
        cls.text = strip_comments(cls.raw)
        cls.runs = run_blocks(cls.raw)
        cls.steps = steps(cls.text)

    def test_single_workflow_file(self):
        names = sorted(path.name for path in WORKFLOWS.iterdir()
                       if path.suffix in (".yml", ".yaml"))
        self.assertEqual(names, ["ci.yml"])

    def test_actions_are_allowed_and_pinned_by_full_sha(self):
        uses = re.findall(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$", self.raw, flags=re.M)
        self.assertTrue(uses)
        for reference, rest in uses:
            action, _, revision = reference.partition("@")
            self.assertIn(action, ALLOWED_ACTIONS)
            self.assertRegex(revision, r"^[0-9a-f]{40}$")
            self.assertRegex(rest, r"^\s+#\s+v\d+\.\d+\.\d+\s*$")
        # every `uses:` is one of the lines checked above (none hides in a flow mapping)
        self.assertEqual(len(re.findall(r"\buses\s*:", self.text)), len(uses))

    def test_every_checkout_does_not_persist_credentials(self):
        checkouts = [step for step in self.steps
                     if any(re.match(r"^\s*(?:-\s+)?uses:\s*actions/checkout@", line)
                            for line in step)]
        self.assertTrue(checkouts)
        self.assertEqual(len(checkouts), len(re.findall(r"actions/checkout@", self.text)))
        for step in checkouts:
            keys = [line.strip() for line in step]
            self.assertIn("with:", keys)
            self.assertIn("persist-credentials: false", keys)
        self.assertEqual(set(re.findall(r"persist-credentials:\s*(\S*)", self.text)), {"false"})

    def test_triggers(self):
        bodies = mapping_bodies(self.text, "on", indent=0)
        self.assertEqual(len(bodies), 1)
        # the whole block: a trigger added after these is caught as well
        self.assertEqual([line.strip() for line in bodies[0]],
                         ["push:", "pull_request:", "workflow_dispatch:"])
        self.assertRegex(self.text, r"(?m)^on:\n  push:\n  pull_request:\n  workflow_dispatch:\n\n")
        self.assertNotIn("pull_request_target", self.raw)
        self.assertNotIn("workflow_run", self.raw)

    def test_read_only_permissions(self):
        self.assertEqual(len(re.findall(r"(?m)^[ \t]*permissions:", self.text)), 1)
        bodies = mapping_bodies(self.text, "permissions", indent=0)
        self.assertEqual(len(bodies), 1)
        self.assertEqual([line.strip() for line in bodies[0]], ["contents: read"])
        self.assertNotRegex(self.text, r":\s*write\b")
        self.assertNotIn("write-all", self.raw)

    def test_workflow_is_written_in_block_style(self):
        """No flow mappings: every key is on a line of its own, where the checks see it."""
        structure = re.sub(r"\$\{\{.*?\}\}", "", outside_run_blocks(self.text))
        self.assertNotIn("{", structure)
        self.assertNotIn("}", structure)
        self.assertEqual(re.findall(r"(?m)^\s+steps:(.*)$", self.text), [""])
        self.assertGreaterEqual(len(self.steps), 5)
        for step in self.steps:
            self.assertRegex(step[0], r"^\s*-\s+[A-Za-z-]+:(\s|$)")

    def test_steps_cannot_be_skipped_or_fail_silently(self):
        self.assertNotIn("continue-on-error", self.raw)
        self.assertNotRegex(self.text, r"(?m)^\s*(?:-\s+)?[\"']?if[\"']?\s*:")

    def test_no_secrets_deploy_or_uploads(self):
        self.assertNotIn("secrets.", self.raw)
        self.assertNotRegex(self.raw, r"(?i)github_token|upload-artifact|deploy-pages")

    def test_expressions_are_limited_to_safe_contexts(self):
        expressions = re.findall(r"\$\{\{\s*(.*?)\s*\}\}", self.raw)
        self.assertTrue(expressions)
        for expression in expressions:
            self.assertRegex(expression, ALLOWED_EXPRESSIONS)
        self.assertNotIn("github.event.", self.raw)

    def test_run_blocks_contain_no_expressions(self):
        self.assertGreaterEqual(len(self.runs), 3)
        for block in self.runs:
            self.assertNotIn("${{", block)
            self.assertNotIn("github.event.", block)

    def test_matrix_and_runner(self):
        matrix = re.search(r"(?m)^\s+python:\s*\[(.*)\]\s*$", self.text)
        self.assertIsNotNone(matrix)
        versions = [item.strip() for item in matrix.group(1).split(",")]
        self.assertEqual(versions, ['"3.10"', '"3.11"', '"3.12"', '"3.13"'])
        # the list is the whole matrix: nothing added or taken away
        bodies = mapping_bodies(self.text, "matrix")
        self.assertEqual(len(bodies), 1)
        self.assertEqual([line.strip() for line in bodies[0]],
                         ['python: ["3.10", "3.11", "3.12", "3.13"]'])
        self.assertNotIn("include:", self.text)
        self.assertNotIn("exclude:", self.text)
        self.assertRegex(self.text, r"(?m)^\s+fail-fast:\s*false$")
        self.assertRegex(self.text, r"(?m)^\s+runs-on:\s*ubuntu-\d+\.\d+$")
        self.assertRegex(self.text, r"(?m)^\s+timeout-minutes:\s*\d+$")

    def test_concurrency_cancels_stale_runs(self):
        self.assertRegex(
            self.text,
            r"(?m)^concurrency:\n  group: .*github\.ref.*\n"
            r"  cancel-in-progress: \$\{\{ github\.ref != 'refs/heads/main' \}\}$",
        )

    def test_hygiene_checks_every_tracked_file_for_media(self):
        hygiene = [block for block in self.runs if "ls-files" in block]
        self.assertEqual(len(hygiene), 1)
        block = hygiene[0]
        listings = re.findall(r"git\b.*?\bls-files\b[^|)]*", block)
        self.assertGreaterEqual(len(listings), 2)
        for listing in listings:
            self.assertRegex(listing, r"^git -c core\.quotePath=false ls-files -z\b")
        self.assertIn("must not contain line breaks or carriage returns", block)
        # the whole tree: no path given to the listing, no directory filtered out
        self.assertIn(f'media="$(tracked | grep -aEi {MEDIA_PATTERN} || true)"', block)
        self.assertNotRegex(block, r"grep\s+-[A-Za-z]*v")
        self.assertIn('output="$(tracked dist)"', block)
        self.assertEqual(block.count("exit 1"), 3)

    def test_unit_tests_run_after_the_hygiene_check(self):
        hygiene = [i for i, block in enumerate(self.runs) if "ls-files" in block]
        tests = [i for i, block in enumerate(self.runs) if "python -m unittest" in block]
        self.assertEqual(len(tests), 1)
        self.assertLess(hygiene[0], tests[0])

    def test_working_tree_stays_clean_at_the_end(self):
        last = self.runs[-1]
        self.assertIn('status="$(git status --porcelain)"', last)
        self.assertIn("exit 1", last)

    def test_no_browser_or_media_tools(self):
        for name in ("chrome", "chromium", "ffmpeg", "apt-get"):
            self.assertNotIn(name, self.raw.lower())


if __name__ == "__main__":
    unittest.main()
