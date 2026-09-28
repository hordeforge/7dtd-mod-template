#!/usr/bin/env python3
"""`ILSPYCMD` is read, and a configured path is the tool that runs.

`ILSPYCMD` is listed in `.local.env.example` and filled in by new-mod.sh
from `command -v`, and nothing read it: `verify-patch-targets.py` searched
`PATH` and then a hardcoded `~/.dotnet/tools`, so a tool recorded on any
other path resolved to "not found" however the file was configured. The
order is now the key, then `PATH`, then the global-tools directory.

Two failure modes the order has to get right, both checked below:

- a key pointing at a file that is not there must be reported as the stale
  value it is, not silently replaced by a different ilspycmd from PATH;
- a key that names a real file must be the executable that runs, which is
  what prepending its directory to PATH buys. Appending left any ilspycmd
  already on PATH ahead of it.

Only the resolver and the environment are touched: nothing is executed, so
the host needs no ilspycmd and no game install.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
KEY = "ILSPYCMD"


def load_verifier() -> ModuleType:
    """Import the hyphenated script by path; it has no package of its own."""
    path = os.path.join(SCRIPT_DIR, "verify-patch-targets.py")
    spec = importlib.util.spec_from_file_location("verify_patch_targets", path)
    if spec is None or spec.loader is None:
        raise SystemExit("ERROR: cannot load " + path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve(verifier: ModuleType, root: Path, *, which: str | None,
            home: Path, environ: dict[str, str] | None = None) -> tuple[str | None, str]:
    """`resolve_ilspycmd` against a throwaway root and a stubbed PATH.

    `which` is what a PATH lookup returns and `home` stands in for the
    global-tools directory, so the three sources are separable without any
    of them existing on this machine.
    """
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(environ or {})
    real_which, real_home = verifier.shutil.which, verifier.Path.home
    verifier.shutil.which = lambda _name: which
    verifier.Path.home = staticmethod(lambda: home)
    try:
        error = verifier.resolve_ilspycmd(root)
        return error, os.environ.get("PATH", "")
    finally:
        verifier.shutil.which, verifier.Path.home = real_which, real_home
        os.environ.clear()
        os.environ.update(previous)


def main() -> int:
    verifier = load_verifier()

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        tool = root / "tools" / "ilspycmd"
        tool.parent.mkdir()
        tool.write_text("#!/bin/sh\n", encoding="utf-8")
        tool.chmod(0o755)
        stale = root / "tools" / "gone"
        # The last-resort directory is <home>/.dotnet/tools, so the stub home
        # carries that nesting rather than the directory itself.
        stub_home = root / "home"
        global_tools = stub_home / ".dotnet" / "tools"
        global_tools.mkdir(parents=True)

        # Negative control: the defect this gate exists for. A key nothing
        # read, with the tool reachable only from the key.
        error, path = resolve(verifier, root, which=None, home=stub_home,
                              environ={KEY: str(tool)})
        check("a configured ILSPYCMD resolves", error is None, str(error))
        check("the configured directory leads PATH", path.startswith(str(tool.parent)),
              path)

        error, _ = resolve(verifier, root, which=None, home=stub_home,
                           environ={KEY: str(stale)})
        check("a stale key is reported, not replaced", error is not None
              and str(stale) in error, str(error))
        check("the stale-key message names the key", error is not None and KEY in error,
              str(error))

        error, _ = resolve(verifier, root, which=None, home=stub_home)
        check("an unset key falls back to PATH", error is not None
              and "dotnet tool install" in error, str(error))

        on_path = root / "on-path" / "ilspycmd"
        on_path.parent.mkdir()
        on_path.write_text("#!/bin/sh\n", encoding="utf-8")
        error, path = resolve(verifier, root, which=str(on_path), home=stub_home)
        check("a PATH lookup is used when the key is unset", error is None, str(error))
        check("the PATH lookup leads PATH", path.startswith(str(on_path.parent)), path)

        installed = global_tools / "ilspycmd"
        installed.write_text("#!/bin/sh\n", encoding="utf-8")
        error, path = resolve(verifier, root, which=None, home=stub_home)
        check("the global-tools directory is the last resort", error is None, str(error))
        check("the global-tools directory leads PATH",
              path.startswith(str(global_tools)), path)

    return report()


if __name__ == "__main__":
    raise SystemExit(main())
