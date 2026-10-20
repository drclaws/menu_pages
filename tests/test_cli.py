"""Tests of the command line of `build.py` (standard library only)."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build  # noqa: E402  (imported after sys.path is prepared)

SCRIPT = ROOT / "build.py"

if Path(build.__file__).resolve() != SCRIPT:  # pragma: no cover
    raise RuntimeError(f"unexpected build module: {build.__file__}")

COMMANDS = ("build", "validate")

#: The width argparse wraps its messages to, the same in and out of process.
COLUMNS = "80"


def run_main(*args: str) -> SimpleNamespace:
    """Run `build.main()` in-process; argparse exits are turned into codes."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        mock.patch.dict(os.environ, {"COLUMNS": COLUMNS}),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        try:
            code = build.main(list(args))
        except SystemExit as exc:  # argparse: --help and usage errors
            code = exc.code if isinstance(exc.code, int) else 2
    return SimpleNamespace(returncode=code, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def subprocess_env() -> dict:
    """The environment of a child Python: UTF-8 output, no bytecode files."""
    environ = dict(os.environ)
    environ["COLUMNS"] = COLUMNS
    environ["PYTHONIOENCODING"] = "utf-8"
    environ["PYTHONDONTWRITEBYTECODE"] = "1"
    return environ


def run_script(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    """Run `python build.py ...` as a script from the directory `cwd`."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd),
        env=subprocess_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class CliTest(unittest.TestCase):
    def test_help_exits_with_zero(self):
        result = run_main("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)
        for command in COMMANDS:
            self.assertIn(command, result.stdout)
        self.assertEqual(result.stderr, "")

    def test_no_command_prints_usage_and_exits_with_two(self):
        result = run_main()
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_commands_are_not_implemented_yet(self):
        for command in COMMANDS:
            with self.subTest(command=command):
                result = run_main(command)
                self.assertEqual(result.returncode, 2)
                self.assertIn("is not implemented yet", result.stderr)
                self.assertEqual(result.stderr, f"error: '{command}' is not implemented yet\n")
                self.assertEqual(result.stdout, "")

    def test_unknown_command_exits_with_two(self):
        result = run_main("deploy")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)
        self.assertNotIn("is not implemented yet", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_commands_take_no_parameters_yet(self):
        for command in COMMANDS:
            with self.subTest(command=command):
                result = run_main(command, "--out", "dist")
                self.assertEqual(result.returncode, 2)
                self.assertIn("unrecognized arguments", result.stderr)
                self.assertNotIn("is not implemented yet", result.stderr)

    def test_import_has_no_output(self):
        with tempfile.TemporaryDirectory(prefix="menu-build-test-") as temporary:
            result = subprocess.run(
                [sys.executable, "-c",
                 "import sys; sys.path.insert(0, sys.argv[1]); import build", str(ROOT)],
                cwd=temporary,
                env=subprocess_env(),
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_script_from_another_directory_behaves_the_same(self):
        cases = (("--help",), (), *((command,) for command in COMMANDS), ("deploy",))
        with tempfile.TemporaryDirectory(prefix="menu-build-test-") as temporary:
            work = Path(temporary).resolve()
            for args in cases:
                with self.subTest(args=args):
                    expected = run_main(*args)
                    result = run_script(*args, cwd=work)
                    self.assertEqual(result.returncode, expected.returncode)
                    self.assertEqual(result.stdout, expected.stdout)
                    self.assertEqual(result.stderr, expected.stderr)
            # nothing is written to the current directory
            self.assertEqual(list(work.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
