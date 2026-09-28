#!/usr/bin/env python3
"""Derive a mod-owned serverconfig.xml with EAC off, for DLL testing.

Copies the dedicated server's own serverconfig.xml and forces
EACEnabled=false, so a mod's Harmony patch is exercised rather than refused
by the anti-cheat. The source must already carry an EACEnabled property;
a vanilla serverconfig that does not is an error, not something to invent.
"""

import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TextIO


def usage(stream: TextIO = sys.stdout) -> None:
    print("Derive a mod-owned serverconfig.xml with EAC off, for DLL testing.", file=stream)
    print(file=stream)
    print("USAGE", file=stream)
    print("  configure-server-config.py SOURCE_CONFIG TARGET_CONFIG", file=stream)
    print(file=stream)
    print("OPTIONS", file=stream)
    print("  -h, --help  show this help and exit", file=stream)
    print(file=stream)
    print("EXIT STATUS", file=stream)
    print("  0  the target is written", file=stream)
    print("  1  the source cannot be used, or the target cannot be written", file=stream)
    print("  2  wrong arguments", file=stream)


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] in ("-h", "--help"):
        usage()
        return 0
    if len(sys.argv) != 3:
        print("ERROR: wrong arguments.", file=sys.stderr)
        usage(sys.stderr)
        return 2

    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    try:
        tree = ET.parse(source)
    except (ET.ParseError, OSError) as exc:
        print(f"ERROR: cannot read {source}: {exc}", file=sys.stderr)
        return 1
    settings = tree.getroot()
    eac = settings.find("property[@name='EACEnabled']")
    if eac is None:
        print(f"ERROR: {source} has no EACEnabled property.", file=sys.stderr)
        return 1

    eac.set("value", "false")
    ET.indent(tree, space="\t")
    # The target is the mod's own config, and the server lane only writes it
    # when it does not exist yet: a write interrupted halfway would leave a
    # truncated file that every later run then trusts and refuses to
    # regenerate. Staging beside it and renaming makes the second run see
    # either the old file or the whole new one.
    staged = None
    try:
        descriptor, staged_name = tempfile.mkstemp(
            dir=target.parent, prefix=target.name + ".", suffix=".tmp"
        )
        os.close(descriptor)
        staged = Path(staged_name)
        tree.write(staged, encoding="utf-8", xml_declaration=True)
        os.replace(staged, target)
    except OSError as exc:
        print(f"ERROR: cannot write {target}: {exc}", file=sys.stderr)
        return 1
    finally:
        if staged is not None and staged.exists():
            staged.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
