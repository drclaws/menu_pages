"""Tests of the bridge to the invitations builder (`menu_tools/_core.py`)."""

import argparse
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build  # noqa: E402  (imported after sys.path is prepared)
from menu_tools import _core as core  # noqa: E402

SITE = (ROOT / "site").resolve()

MISSING_ERROR = (
    "error: the invitations builder is missing in site/: "
    "run git submodule update --init --recursive\n"
)

#: Prints, as JSON, what a fresh interpreter sees after loading the bridge.
PROBE = """
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from menu_tools import _core
import build, tools
site = Path(sys.argv[1], "site").resolve()
print(json.dumps({
    "site_on_path": [p for p in sys.path if Path(p or ".").resolve() == site],
    "build": build.__file__,
    "tools": tools.__file__,
    "invitations": sys.modules["invitations_build"].__file__,
}))
"""

#: Imports the bridge of the copy in `argv[1]` and prints, as JSON, how that
#: went; with `argv[2]`, the package `tools` of that directory is imported first.
IMPORT_BRIDGE = """
import json, sys
from pathlib import Path
root = sys.argv[1]
sys.path.insert(0, root)
if len(sys.argv) > 2:
    sys.path.insert(0, sys.argv[2])
    import tools  # a package of another project
try:
    from menu_tools import _core
except ImportError as exc:
    result = {"error": type(exc).__name__, "name": exc.name, "message": str(exc)}
except Exception as exc:
    result = {"error": type(exc).__name__, "name": None, "message": str(exc)}
else:
    result = {"error": None}
site = Path(root, "site").resolve()
result["site_on_path"] = [p for p in sys.path if Path(p or ".").resolve() == site]
result["loaded"] = "invitations_build" in sys.modules
print(json.dumps(result))
"""


def subprocess_env() -> dict:
    """The environment of a child Python: UTF-8 output, no bytecode files."""
    environ = dict(os.environ)
    environ["PYTHONIOENCODING"] = "utf-8"
    environ["PYTHONDONTWRITEBYTECODE"] = "1"
    return environ


def run_python(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run a child Python with `args` in the directory `cwd`."""
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(cwd),
        env=subprocess_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def copy_menu(destination: Path) -> Path:
    """Copy the code of the menu (not `site/`) to `destination/menu`."""
    root = destination / "menu"
    (root / "menu_tools").mkdir(parents=True)
    shutil.copy2(ROOT / "build.py", root / "build.py")
    for source in sorted((ROOT / "menu_tools").glob("*.py")):
        shutil.copy2(source, root / "menu_tools" / source.name)
    return root


def invitations_modules() -> dict:
    """{name: module} of the invitations the bridge takes its names from."""
    return {
        "build": core._build,
        "tools._data": core._data,
        "tools._schema": core._schema,
        "tools._tokens": core._tokens,
        "tools.gen_assets": core._gen_assets,
    }


def resolve_internal(qualified: str):
    """The object an entry of `INTERNAL_NAMES` names, e.g. `build._StagedOutput`."""
    module_name, _, name = qualified.rpartition(".")
    module = core._build if module_name == "build" else importlib.import_module(module_name)
    return name, getattr(module, name)


class BridgeLoadTest(unittest.TestCase):
    def test_the_builder_is_loaded_from_the_submodule(self):
        invitations = core._build
        self.assertEqual(invitations.__name__, "invitations_build")
        self.assertEqual(Path(invitations.__file__).resolve(), SITE / "build.py")
        self.assertIs(sys.modules["invitations_build"], invitations)
        self.assertEqual(invitations.CODE_DIR, SITE)

    def test_tools_is_the_package_of_the_submodule(self):
        tools = sys.modules["tools"]
        self.assertEqual(Path(tools.__file__).resolve(), SITE / "tools" / "__init__.py")
        for module in invitations_modules().values():
            with self.subTest(module=module.__name__):
                self.assertTrue(Path(module.__file__).resolve().is_relative_to(SITE))

    def test_site_is_not_left_on_the_path(self):
        self.assertEqual([p for p in sys.path if Path(p or ".").resolve() == SITE], [])

    def test_import_build_is_the_entry_point_of_the_menu(self):
        self.assertEqual(Path(build.__file__).resolve(), ROOT / "build.py")
        self.assertIsNot(build, core._build)

    def test_a_fresh_interpreter_sees_the_same(self):
        with tempfile.TemporaryDirectory(prefix="menu-core-test-") as temporary:
            result = run_python("-c", PROBE, str(ROOT), cwd=Path(temporary))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        seen = json.loads(result.stdout)
        self.assertEqual(seen["site_on_path"], [])
        self.assertEqual(Path(seen["build"]).resolve(), ROOT / "build.py")
        self.assertEqual(Path(seen["tools"]).resolve(), SITE / "tools" / "__init__.py")
        self.assertEqual(Path(seen["invitations"]).resolve(), SITE / "build.py")

    def test_loading_again_gives_the_same_module(self):
        self.assertIs(core._load(), core._build)


class ExportsTest(unittest.TestCase):
    def test_every_exported_name_comes_from_the_invitations(self):
        self.assertEqual(len(core.__all__), len(set(core.__all__)))
        modules = invitations_modules()
        aliases = {"SCHEMA_MISSING": ("tools._schema", "MISSING")}
        missing = object()
        for name in core.__all__:
            with self.subTest(name=name):
                value = getattr(core, name)
                if name in aliases:
                    module_name, source = aliases[name]
                    self.assertIs(value, getattr(modules[module_name], source))
                    continue
                origins = [module_name for module_name, module in modules.items()
                           if getattr(module, name, missing) is value]
                self.assertTrue(origins, f"{name} is not a name of the invitations")

    def test_names_with_two_meanings_come_from_the_right_module(self):
        self.assertIs(core.MISSING, core._build.MISSING)
        self.assertIs(core.SCHEMA_MISSING, core._schema.MISSING)
        self.assertIsNot(core.MISSING, core.SCHEMA_MISSING)
        # of a style sheet, not the one of build.py (a directory of assets)
        self.assertIs(core.load_palette, core._tokens.load_palette)
        self.assertIsNot(core.load_palette, core._build.load_palette)

    def test_every_internal_name_still_exists(self):
        self.assertTrue(core.INTERNAL_NAMES)
        for qualified in core.INTERNAL_NAMES:
            with self.subTest(name=qualified):
                name, value = resolve_internal(qualified)
                self.assertTrue(name.startswith("_"))
                self.assertIs(getattr(core, name), value)

    def test_internal_names_list_every_exported_internal_name(self):
        exported = {name for name in core.__all__ if name.startswith("_")}
        listed = {qualified.rpartition(".")[2] for qualified in core.INTERNAL_NAMES}
        self.assertEqual(exported, listed)

    def test_the_sentinels_are_what_the_helpers_return(self):
        report = core.Report()
        checker = core._Checker(report, "menu.json")
        self.assertIs(checker.value({}, "title", "string", ()), core.SCHEMA_MISSING)
        self.assertEqual(report.errors, [])
        with tempfile.TemporaryDirectory(prefix="menu-core-test-") as temporary:
            absent = Path(temporary) / "menu.json"
            self.assertIs(core.read_json(absent, report), core.MISSING)
        self.assertEqual(len(report.errors), 1)
        self.assertTrue(report.errors[0].endswith(": file not found"), report.errors)

    def test_exit_codes(self):
        self.assertEqual((core.EXIT_OK, core.EXIT_ERROR, core.EXIT_USAGE), (0, 1, 2))

    def test_the_argument_types_keep_good_values(self):
        self.assertEqual(core.token_prefix("heron"), "heron")
        self.assertEqual(core.parse_published_url("https://example.org/menu/"), "https://example.org/menu")
        self.assertEqual(core.base_path_argument("/menu"), "/menu")

    def test_the_argument_types_do_not_repeat_the_value(self):
        # a refused value may be private (a name in a prefix, credentials in
        # an address): the message names the problem, never the value
        cases = (
            (core.token_prefix, "Rosalind and Leopold"),
            (core.token_prefix, "Wendell" * 40),
            (core.parse_published_url, "https://wendell:hunter-secret@example.org/menu"),
            (core.parse_published_url, "ftp://bjarne-host.example.org/menu"),
            (core.parse_published_url, "https://example.org/menu?judy=1"),
            (core.base_path_argument, "/rosalind path"),
            (core.base_path_argument, "/leopold path"),
        )
        for convert, value in cases:
            with self.subTest(convert=convert.__name__, value=value):
                with self.assertRaises(argparse.ArgumentTypeError) as caught:
                    convert(value)
                message = str(caught.exception)
                self.assertTrue(message)
                self.assertNotIn(value, message)
                for word in re.findall(r"[A-Za-z]{4,}", value):
                    if word not in ("https", "example", "menu", "path"):
                        self.assertNotIn(word.lower(), message.lower())

    def test_the_reserved_tokens_are_refused_by_the_token_check(self):
        self.assertTrue(core.RESERVED_TOKENS)
        for token in core.RESERVED_TOKENS:
            with self.subTest(token=token):
                self.assertIsNotNone(core.check_token(token))
                self.assertIsNotNone(core.check_token(token.upper()))

    def test_the_colour_of_a_token_is_written_as_hex(self):
        self.assertEqual(core.hex_color((250, 247, 242)), "#faf7f2")
        self.assertTrue(issubclass(core.TokenError, ValueError))


class WithoutTheSubmoduleTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="menu-core-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.root = copy_menu(self.work)

    def assert_missing_message(self, result):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr, MISSING_ERROR)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)

    def test_validate_prints_the_message_and_exits_with_one(self):
        result = run_python(str(self.root / "build.py"), "validate", cwd=self.work)
        self.assert_missing_message(result)

    def test_an_empty_submodule_directory_gives_the_same_message(self):
        (self.root / "site").mkdir()
        commands = (
            ("build",),
            ("build", "--base-path", "/menu"),
            ("validate",),
            ("links", "--url", "https://example.org/menu"),
            ("token",),
            ("token", "--prefix", "heron"),
        )
        for command in commands:
            with self.subTest(command=command):
                result = run_python(str(self.root / "build.py"), *command, cwd=self.work)
                self.assert_missing_message(result)

    def test_help_still_works(self):
        result = run_python(str(self.root / "build.py"), "--help", cwd=self.work)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_the_bridge_raises_an_import_error_named_after_the_module(self):
        result = run_python("-c", IMPORT_BRIDGE, str(self.root), cwd=self.work)
        self.assertEqual(result.returncode, 0, result.stderr)
        outcome = json.loads(result.stdout)
        self.assertEqual(outcome["error"], "CoreError")
        self.assertEqual(outcome["name"], "invitations_build")
        self.assertEqual(outcome["message"], core.MISSING_MESSAGE)
        self.assertEqual(MISSING_ERROR, f"error: {core.MISSING_MESSAGE}\n")
        self.assertFalse(outcome["loaded"])


class LoaderSafetyTest(unittest.TestCase):
    """The loader on a stand-in for the submodule and another `tools` package."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="menu-core-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.root = copy_menu(self.work)
        site = self.root / "site"
        (site / "tools").mkdir(parents=True)
        (site / "tools" / "__init__.py").write_text("", encoding="utf-8")
        # imports its own package, as the real script does
        (site / "build.py").write_text("import tools\n", encoding="utf-8")

    def import_bridge(self, *args: str) -> dict:
        result = run_python("-c", IMPORT_BRIDGE, str(self.root), *args, cwd=self.work)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def other_tools(self) -> Path:
        other = self.work / "other"
        (other / "tools").mkdir(parents=True)
        (other / "tools" / "__init__.py").write_text("", encoding="utf-8")
        return other

    def test_the_loader_accepts_the_stand_in(self):
        # loaded, and site/ is off the path again; the bridge then stops at the
        # first module the stand-in lacks, which is not the bridge's own error
        outcome = self.import_bridge()
        self.assertTrue(outcome["loaded"])
        self.assertEqual(outcome["site_on_path"], [])
        self.assertEqual(outcome["error"], "ImportError")
        self.assertEqual(outcome["name"], "tools")

    def test_a_fault_of_the_code_is_a_traceback_at_the_entry_point(self):
        result = run_python(str(self.root / "build.py"), "validate", cwd=self.work)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Traceback", result.stderr)
        self.assertIn("ImportError: cannot import name", result.stderr)

    def test_another_tools_package_already_imported_is_refused(self):
        outcome = self.import_bridge(str(self.other_tools()))
        self.assertEqual(outcome["error"], "CoreError")
        self.assertEqual(outcome["name"], "invitations_build")
        self.assertEqual(outcome["message"], core.CONFLICT_MESSAGE)
        self.assertEqual(outcome["site_on_path"], [])
        self.assertFalse(outcome["loaded"])

    def test_a_script_that_brings_another_tools_package_is_refused(self):
        package = self.other_tools() / "tools" / "__init__.py"
        (self.root / "site" / "build.py").write_text(
            "import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('tools', {str(package)!r})\n"
            "sys.modules['tools'] = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(sys.modules['tools'])\n",
            encoding="utf-8",
        )
        outcome = self.import_bridge()
        self.assertEqual(outcome["error"], "CoreError")
        self.assertEqual(outcome["message"], core.CONFLICT_MESSAGE)
        self.assertEqual(outcome["site_on_path"], [])
        self.assertFalse(outcome["loaded"])

    def test_a_failing_script_leaves_neither_the_module_nor_the_path(self):
        (self.root / "site" / "build.py").write_text(
            "raise RuntimeError('broken')\n", encoding="utf-8")
        outcome = self.import_bridge()
        self.assertEqual(outcome["error"], "RuntimeError")
        self.assertEqual(outcome["message"], "broken")
        self.assertEqual(outcome["site_on_path"], [])
        self.assertFalse(outcome["loaded"])


if __name__ == "__main__":
    unittest.main()
