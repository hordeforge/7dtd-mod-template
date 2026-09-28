#!/usr/bin/env python3
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: configure-server-config.py SOURCE_CONFIG TARGET_CONFIG", file=sys.stderr)
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
        print("ERROR: server configuration has no EACEnabled property.", file=sys.stderr)
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
