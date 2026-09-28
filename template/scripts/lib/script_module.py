"""Load a hyphenated `scripts/*.py` as a module.

The tools here are named `verify-patch-targets.py` and
`validate-xml-targets.py`, which no `import` statement can name, so the
offline gates that drive them load them by path instead. Four gates do that,
and the four copies had drifted: one asserted `spec.loader is not None` (an
`assert`, stripped under `python -O`), one dereferenced a `None` spec
unchecked, and two raised a `SystemExit` naming the path. Import this by
putting this directory on the path; a caller in `scripts/` does:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from script_module import load_script
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_script(path: Path, name: str) -> ModuleType:
    """`path` executed as a module called `name`.

    A path that yields no loader is fatal and names itself: an `ImportError`
    out of a gate reports the import machinery, not which of the tree's
    tools could not be loaded.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"ERROR: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
