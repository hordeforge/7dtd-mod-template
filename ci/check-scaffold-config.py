#!/usr/bin/env python3
"""What a scaffold config may hold, and what the scaffolder does with it.

`newmod.conf.example` is a shell file a person edits, so the three ways it
can be wrong are all quiet until a mod is half built: a key spelled with one
wrong letter, a yes/no key holding anything but `yes` or `no`, and a value
the run takes no further care of. The first two are already hard errors; this
gate holds them there and pins the two rules around them that nothing else
covers:

* an empty value is "not set", for every optional key. `display_name=""`
  takes the mod name and `csharp=""` takes its default, because a config that
  blanks a key to say "the default" is what `newmod.conf.example` does on
  every line. A yes/no key that read empty as an error made the one spelling
  the example teaches fail on the two keys it teaches it on.
* every key the scaffolder writes into a new mod's `.local.env` is listed in
  the mod's `.local.env.example`, so a generated key can never be one no
  document describes its valid values for.

Nothing is written outside `.scratch/`, and the scaffolded mods are removed
when the run ends.

Usage: ci/check-scaffold-config.py
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys

FAILURES: list[str] = []

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAFFOLDER = os.path.join(ROOT, "new-mod.sh")
EXAMPLE = os.path.join(ROOT, "template", ".local.env.example")
WORK = os.path.join(ROOT, ".scratch", "anvil-config")
MODS = os.path.join(WORK, "mods")

# The `KEY="value"` line of a `.local.env`, and of the example that documents it.
ASSIGNMENT = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*)=")

# The keys every config below starts from, so a case reads as the one thing
# it changes. `author` is the one that a case can leave out.
BASE = (
    'purpose="A purpose."\n'
    'target_dir="{mods}"\n'
    'hordeforge_root="{root}"\n'
    'clone="no"\n'
)


def check(name: str, ok: bool, detail: str = "") -> None:
    """Record one assertion; `detail` explains a failure and is dropped on a pass."""
    if ok:
        print("PASS " + name)
    else:
        FAILURES.append(name)
        print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def scaffold(name: str, config_body: str, author: bool = True) -> tuple[int, str, str]:
    """Run the scaffolder on a config; return its status, its output, the mod dir."""
    os.makedirs(WORK, exist_ok=True)
    mod_dir = os.path.join(MODS, name)
    config = os.path.join(WORK, name + ".conf")
    base = BASE.format(mods=MODS, root=os.path.join(WORK, "hordeforge"))
    with open(config, "w", encoding="utf-8", newline="") as handle:
        handle.write(f'name="{name}"\n')
        if author:
            handle.write('author="CI Config"\n')
        handle.write(base + config_body)
    # stdin closed: a config missing a required key has to fail here rather
    # than block on a prompt nobody is there to answer.
    result = subprocess.run(
        [SCAFFOLDER, config], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False, cwd=ROOT,
        stdin=subprocess.DEVNULL)
    return result.returncode, result.stdout + result.stderr, mod_dir


def documented_keys() -> set[str]:
    """Every key `template/.local.env.example` lists."""
    with open(EXAMPLE, encoding="utf-8-sig") as handle:
        return {match["key"] for line in handle
                for match in [ASSIGNMENT.match(line)] if match}


def written_keys(local_env: str) -> list[str]:
    """Every key the scaffolder wrote into a new mod's `.local.env`."""
    with open(local_env, encoding="utf-8-sig") as handle:
        return [match["key"] for line in handle
                for match in [ASSIGNMENT.match(line)] if match]


def main() -> int:
    if not os.access(SCAFFOLDER, os.X_OK):
        print(f"ERROR: {SCAFFOLDER} is not executable", file=sys.stderr)
        return 2

    # An empty value is "not set" for every optional key, so the two feature
    # keys take the defaults the example documents: no C# project, no assets.
    status, output, mod_dir = scaffold("ConfigDefaults", 'csharp=""\nassets=""\n')
    check("an empty yes/no key takes its default", status == 0, f"exited {status}: {output[-300:]}")
    if status == 0:
        check("csharp defaults to no", not os.path.exists(os.path.join(mod_dir, "src")))
        check("assets defaults to no", not os.path.exists(os.path.join(mod_dir, "assets-src")))

        # The keys a new mod's machine-local configuration is written with are
        # the ones the mod's own example documents, so a generated key is
        # never one no document describes.
        local_env = os.path.join(mod_dir, ".local.env")
        written = written_keys(local_env)
        missing = sorted(set(written) - documented_keys())
        check("every generated .local.env key is documented", not missing, ", ".join(missing))
        check("the generated .local.env is not empty", bool(written), local_env)
        # It names this account's home and install directories.
        mode = stat.S_IMODE(os.stat(local_env).st_mode)
        check("the generated .local.env is 0600", mode == 0o600, oct(mode))

    # A yes/no key holding anything else takes the else branch and scaffolds a
    # mod quietly missing a feature, or a server that is never installed.
    status, output, mod_dir = scaffold("ConfigBadFlag", 'csharp="true"\nassets="no"\n')
    check("a yes/no key outside yes/no is refused", status == 2, f"exited {status}")
    check("a refused yes/no value writes no mod", not os.path.exists(mod_dir), mod_dir)
    check("the refusal names the key and its value",
          "csharp" in output and "true" in output, output[-300:])

    # The config is sourced, so a misspelled key sets a variable nothing reads
    # and the run quietly takes the default for it.
    unknown = 'csharp="no"\nassets="no"\ncsharp_lang="yes"\n'
    status, output, mod_dir = scaffold("ConfigUnknownKey", unknown)
    check("an unknown key is refused", status == 2, f"exited {status}")
    check("an unknown key writes no mod", not os.path.exists(mod_dir), mod_dir)
    check("the refusal names the key", "csharp_lang" in output, output[-300:])

    # A required key nothing can answer for stops the run before anything is
    # written, and says which key and what it owes.
    status, output, mod_dir = scaffold("ConfigNoAuthor", 'csharp="no"\nassets="no"\n', author=False)
    check("a missing required key is refused", status == 2, f"exited {status}")
    check("a missing required key writes no mod", not os.path.exists(mod_dir), mod_dir)
    check("the refusal names the missing key and what it owes",
          "author" in output and "not running interactively" in output, output[-300:])

    # A path holding a line break cannot be written as KEY="value" at all: the
    # break ends that line, and every server target sources .local.env, so the
    # rest of the value would be read as shell. Refused before the file exists.
    status, output, mod_dir = scaffold(
        "ConfigPathBreak", "game_dir=$'/srv/7dtd\\ntouch pwned'\n")
    check("a path holding a line break is refused", status == 2, f"exited {status}")
    check("a refused line break writes no mod", not os.path.exists(mod_dir), mod_dir)
    check("the refusal names the key", "game_dir" in output, output[-300:])

    shutil.rmtree(WORK, ignore_errors=True)
    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
