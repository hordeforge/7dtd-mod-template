"""The mod's own `Config/` tree, listed the way the engine loads it.

One walk shared by `scripts/validate-xml-targets.py` (does this patch's
xpath match vanilla?) and `scripts/verify-patched-config.py` (did the
running game's own config come out with this mod's elements in it?). The
two answer different questions about the same set of files, so the set is
defined once here: a second copy of the walk is a listing that can drift
into the flat scan that never opens a nested patch.
Import it by putting this directory on the path; a caller in `scripts/`
does:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
    from config_files import patch_files
"""

from __future__ import annotations

import glob
import os


def patch_files(config_dir: str) -> list[str]:
    """Every patch file under `config_dir`, by its path relative to it, sorted.

    Recursive because the engine loads "<mod>/Config/" plus the vanilla
    file's own relative name, so the XUi patches live a directory down
    (Config/XUi_InGame/windows.xml). A flat listing skips every one of them,
    and a skipped patch applies silently: the same failure the callers
    exist to catch. Paths come back with `/` separators because they are
    joined onto the vanilla tree's own names.
    """
    pattern = os.path.join(config_dir, "**", "*.xml")
    return sorted(
        os.path.relpath(path, config_dir).replace(os.sep, "/")
        for path in glob.glob(pattern, recursive=True)
    )
