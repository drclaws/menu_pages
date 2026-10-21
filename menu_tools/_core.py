"""Bridge to the invitations builder checked out in the `site/` submodule.

The menu reuses what the invitations builder already has: the template
engine, the messages of the data checks, the checks of the finished output,
the handling of the output directory, the masking of tokens, the design token
parser and the icon.  A pinned commit of that builder is the submodule
`site/`; everything the menu takes from it goes through this module, so
`__all__` below is the whole surface the menu depends on.

The invitations builder is a script, `site/build.py`, with a package next to
it, `site/tools/`, which all of its modules import as the top-level package
`tools` (`from tools import ...`).  Two names would clash with a plain import:

* `build` - this repository has an entry point `build.py` of its own, whose
  directory comes first on `sys.path`, so `import build` is always the menu's.
  The invitations' script is loaded from its file under the module name
  `invitations_build` instead.
* `tools` - once the script is loaded, `sys.modules["tools"]` is the package
  of the invitations, so the package of the menu cannot have that name (it is
  `menu_tools`).  The loader checks that `tools` is the package of `site/`.

The directory `site/` is first on `sys.path` only while the script loads, so
that its `tools` package wins over anything else of that name, and is taken
away right after: the package stays in `sys.modules`, which is all later
imports need.

Every name is the one it has in the invitations, so its documentation there
applies as is.  The one alias is `SCHEMA_MISSING`: `tools._schema.MISSING`,
what the methods of `_Checker` return for a field without a usable value
(`MISSING` is the one of `site/build.py`, returned by `read_json`).  Names with
a leading underscore are internal to the invitations; `INTERNAL_NAMES` lists
them, and the tests fail when a new pin no longer has one.

Importing this module loads the invitations builder, which has no side effects
on import.  Without the submodule it raises `CoreError`, whose message says
what to do.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

#: The root of the menu repository and the submodule with the invitations builder.
ROOT = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT / "site"

#: The module name the invitations' `build.py` is loaded under.
MODULE_NAME = "invitations_build"

MISSING_MESSAGE = (
    "the invitations builder is missing in site/: "
    "run git submodule update --init --recursive"
)
CONFLICT_MESSAGE = (
    "a package named 'tools' that is not site/tools is already imported: "
    "the invitations builder in site/ needs that name for its own package"
)


class CoreError(ImportError):
    """The invitations builder cannot be loaded; the message says what to do.

    It is an `ImportError` named after the module (`name` is `MODULE_NAME`),
    so the entry point tells it from a fault in the code itself.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, name=MODULE_NAME)


def _is_package_of(module: ModuleType | None, directory: Path) -> bool:
    """True when `module` is the package whose directory is `directory`."""
    location = getattr(module, "__file__", None)
    return location is not None and Path(location).resolve().parent == directory


def _load() -> ModuleType:
    """The module of `site/build.py`, loaded once under `MODULE_NAME`."""
    loaded = sys.modules.get(MODULE_NAME)
    if loaded is not None:
        return loaded
    script = SITE_DIR / "build.py"
    if not script.is_file():
        raise CoreError(MISSING_MESSAGE)
    script = script.resolve()
    tools_dir = (script.parent / "tools").resolve()
    if "tools" in sys.modules and not _is_package_of(sys.modules["tools"], tools_dir):
        raise CoreError(CONFLICT_MESSAGE)
    # The very entry the script looks for before it adds its own directory.
    entry = str(script.parent)
    sys.path.insert(0, entry)
    try:
        spec = importlib.util.spec_from_file_location(MODULE_NAME, script)
        module = importlib.util.module_from_spec(spec)
        # in sys.modules before it runs: dataclasses look their module up there
        sys.modules[MODULE_NAME] = module
        try:
            spec.loader.exec_module(module)
            if not _is_package_of(sys.modules.get("tools"), tools_dir):
                raise CoreError(CONFLICT_MESSAGE)
        except BaseException:
            sys.modules.pop(MODULE_NAME, None)
            raise
    finally:
        sys.path.remove(entry)  # the first occurrence: the one inserted above
    return module


_build = _load()

# The package of the invitations (`site/tools`), already in `sys.modules`.
from tools import _data, _schema, _tokens  # noqa: E402
from tools import gen_assets as _gen_assets  # noqa: E402

# --- template engine ---------------------------------------------------------
Fragments = _build.Fragments
Template = _build.Template
parse_template = _build.parse_template
render = _build.render
check_rendered = _build.check_rendered
load_fragments = _build.load_fragments
load_template = _build.load_template
strip_html_comments = _build.strip_html_comments
text_to_html = _build.text_to_html

# --- errors and the report of a command --------------------------------------
BuildError = _build.BuildError
TemplateError = _build.TemplateError
ValidationError = _build.ValidationError
Report = _build.Report
MISSING = _build.MISSING

# --- data: JSON, paths in messages, ids, tokens ------------------------------
read_json = _build.read_json
parse_json = _data.parse_json
format_path = _data.format_path
show_key = _data.show_key
did_you_mean = _data.did_you_mean
is_identifier = _data.is_identifier
show_id = _data.show_id
ID_RULE = _data.ID_RULE
check_token = _data.check_token
generate_token = _data.generate_token
generate_prefixed_token = _data.generate_prefixed_token
check_token_prefix = _data.check_token_prefix
json_type = _data.json_type

# --- messages of the schema checks -------------------------------------------
_Checker = _schema._Checker
report_warning = _schema.report_warning
SCHEMA_MISSING = _schema.MISSING

# --- checks of the output, the output directory, masking ---------------------
check_output = _build.check_output
check_html = _build.check_html
check_stylesheet = _build.check_stylesheet
check_svg = _build.check_svg
check_base_path = _build.check_base_path
check_allow_paths = _build.check_allow_paths
assets_url_path = _build.assets_url_path
base_path_argument = _build.base_path_argument
redact_tokens = _build.redact_tokens
display_path = _build.display_path
check_out_dir = _build.check_out_dir
check_replaceable = _build.check_replaceable
copy_assets = _build.copy_assets
write_pages = _build.write_pages
OutputError = _build.OutputError
OutputStats = _build.OutputStats
_StagedOutput = _build._StagedOutput

# --- design tokens and the icon ----------------------------------------------
parse_tokens = _tokens.parse_tokens
load_palette = _tokens.load_palette  # of a style sheet (not `build.load_palette`)
palette_from_tokens = _tokens.palette_from_tokens
favicon_svg = _gen_assets.favicon_svg

# --- command line ------------------------------------------------------------
running_in_ci = _build.running_in_ci
EXIT_OK = _build.EXIT_OK
EXIT_ERROR = _build.EXIT_ERROR
EXIT_USAGE = _build.EXIT_USAGE

#: Everything the menu takes from the invitations builder.
__all__ = [
    # template engine
    "Fragments",
    "Template",
    "parse_template",
    "render",
    "check_rendered",
    "load_fragments",
    "load_template",
    "strip_html_comments",
    "text_to_html",
    # errors and the report
    "BuildError",
    "TemplateError",
    "ValidationError",
    "Report",
    "MISSING",
    # data
    "read_json",
    "parse_json",
    "format_path",
    "show_key",
    "did_you_mean",
    "is_identifier",
    "show_id",
    "ID_RULE",
    "check_token",
    "generate_token",
    "generate_prefixed_token",
    "check_token_prefix",
    "json_type",
    # schema messages
    "_Checker",
    "report_warning",
    "SCHEMA_MISSING",
    # output checks, output directory, masking
    "check_output",
    "check_html",
    "check_stylesheet",
    "check_svg",
    "check_base_path",
    "check_allow_paths",
    "assets_url_path",
    "base_path_argument",
    "redact_tokens",
    "display_path",
    "check_out_dir",
    "check_replaceable",
    "copy_assets",
    "write_pages",
    "OutputError",
    "OutputStats",
    "_StagedOutput",
    # design tokens and the icon
    "parse_tokens",
    "load_palette",
    "palette_from_tokens",
    "favicon_svg",
    # command line
    "running_in_ci",
    "EXIT_OK",
    "EXIT_ERROR",
    "EXIT_USAGE",
]

#: The internal names of the invitations (with a leading `_`) the bridge relies
#: on, as `<module>.<name>` (`build` is `site/build.py`): a pin that renames or
#: drops one of them needs a change here.
INTERNAL_NAMES = (
    "build._StagedOutput",
    "tools._schema._Checker",
)
