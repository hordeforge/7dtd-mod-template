#!/usr/bin/env python3
"""A failing decompile must fail one target check, not the whole run.

`verify-patch-targets.py` reports a per-target problem and carries on; a
raised `subprocess.TimeoutExpired` or `OSError` is not that. The caller
handles `RuntimeError` only, so either one escaped as a traceback that
killed the verifier partway through its target list and reported nothing
about the targets it never reached — the silent-green shape this suite
exists to prevent, one hung engine type away.

`subprocess.run` is replaced, so nothing is executed and the answer does
not depend on the host's ilspycmd.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSEMBLY = "Assembly-CSharp.dll"


def load_verifier():
    """Import the hyphenated script by path; it has no package of its own."""
    path = os.path.join(SCRIPT_DIR, "verify-patch-targets.py")
    spec = importlib.util.spec_from_file_location("verify_patch_targets", path)
    if spec is None or spec.loader is None:
        raise SystemExit("ERROR: cannot load " + path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    verifier = load_verifier()
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if ok:
            print("PASS " + name)
            return
        failures.append(name)
        print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)

    real_run = subprocess.run

    def raising(exception):
        def run(*_args, **_kwargs):
            raise exception
        return run

    def timed_out(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=["ilspycmd"], returncode=0, stdout="", stderr="")

    def exits_with(code: int, stderr: str):
        def run(*_args, **_kwargs):
            return subprocess.CompletedProcess(
                args=["ilspycmd"], returncode=code, stdout="", stderr=stderr)
        return run

    for name, patch, needle, subject in (
        ("a decompile timeout", raising(subprocess.TimeoutExpired(["ilspycmd"], 300)),
         "timed out", "Game"),
        ("ilspycmd cannot be launched",
         raising(OSError("No such file or directory")), "No such file", "Game"),
        ("ilspycmd exits non-zero", exits_with(1, "boom"), "boom", "Game"),
        ("the runtime probe times out",
         raising(subprocess.TimeoutExpired(["ilspycmd"], 60)), "did not answer", None),
        ("the runtime probe cannot be launched",
         raising(OSError("Permission denied")), "launched", None),
    ):
        cache: dict[str, list[str]] = {}
        verifier.subprocess.run = patch
        try:
            if subject is None:
                try:
                    probe = verifier.probe_ilspy()
                    ok = probe[0] is None and needle in probe[1]
                    detail = repr(probe)
                except Exception as exc:  # a raw escape is the defect
                    ok, detail = False, f"{type(exc).__name__}: {exc}"
            else:
                try:
                    verifier.decompile(verifier.Path(ASSEMBLY), subject, cache)
                    ok, detail = False, "returned instead of raising"
                except RuntimeError as exc:
                    ok = needle in str(exc)
                    detail = str(exc)
                except Exception as exc:
                    ok, detail = False, f"escaped as {type(exc).__name__}: {exc}"
        finally:
            verifier.subprocess.run = real_run
        check(name + " is a handled RuntimeError naming the type", ok, detail)
        check(name + " leaves the decompile cache unpolluted", cache == {}, repr(cache))

    # A type that decompiles fine must still cache and return its lines.
    cache = {}
    verifier.subprocess.run = timed_out
    try:
        body = verifier.decompile(verifier.Path(ASSEMBLY), "World", cache)
    finally:
        verifier.subprocess.run = real_run
    check("a successful decompile caches and returns its body",
          body == [] and cache == {"World": []}, repr(cache))

    print(f"{len(failures)} failures.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
