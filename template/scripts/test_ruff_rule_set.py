#!/usr/bin/env python3
"""The ruff rule set cannot quietly shrink: every defect group stays selected.

`ruff.toml` is the mod's whole Python analysis posture, and a select list
only defends what it names. Deleting one line of it turns a class of real
defects into findings nobody sees, and nothing else in the tree notices: the
gate still runs, still passes, and reports a clean bill of health for the
rules that happen to be left. A prose promise in AGENTS.md does not survive
that; a check that fails does, so the list is pinned here.

Each group below is one `ruff check` already passes on this tree (proven
before it was added), so holding new code to it costs nothing today and
catches a real defect tomorrow. A group may be added to `REQUIRED` freely
once it passes; removing one needs this file edited in the same change, which
is the point.

Also pinned: the `line-length` cap (ruff's formatter is not run, so an
uncapped line is unstyleable rather than merely unformatted), the
`target-version` floor (it decides which pyupgrade rewrites and which
runtime errors a PEP 604 union raises), and the fact that no required group
is re-disabled through `[lint] ignore` a few lines further down.

Stdlib-only: `tomllib` is 3.11 and this tree runs on 3.9, and the config is
a flat string list this file can read without a TOML parser. Fixture source
is inline and never touches the shipped config.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(MOD_DIR, "ruff.toml")
GATE = os.path.join(MOD_DIR, "scripts", "lint-py.sh")

# Every group the shipped rule set must name, in ruff.toml's own order.
REQUIRED = (
    "E",     # pycodestyle errors
    "W",     # pycodestyle warnings
    "F",     # pyflakes
    "I",     # import order
    "B",     # flake8-bugbear
    "A",     # flake8-builtins
    "ANN",   # every def carries a signature
    "C4",    # comprehensions
    "PIE",   # misc lints
    "PT",    # pytest style
    "PLE",   # pylint errors
    "PLW",   # pylint warnings
    "RET",   # return handling
    "SIM",   # simplifications
    "UP",    # pyupgrade
    "ISC",   # implicit string concat
    "ICN",   # import conventions
    "ARG",   # unused arguments
    "DTZ",   # naive datetimes
    "ERA",   # commented-out code
    "G",     # logging format
    "PGH",   # blanket noqa / type: ignore
    "RSE",   # redundant parens on raise
    "TID",   # relative imports
    "RUF",   # ruff's own rules, RUF100 among them
)

_LIST = re.compile(r"^(?P<key>select|ignore)\s*=\s*\[(?P<body>[^\]]*)\]", re.M | re.S)
_STRING = re.compile(r'"([^"]+)"')


def list_of(source: str, key: str) -> list[str]:
    """The quoted entries of the `key = [...]` list in *source*."""
    for match in _LIST.finditer(source):
        if match.group("key") == key:
            return _STRING.findall(match.group("body"))
    return []


def missing(source: str) -> list[str]:
    """Required groups *source* fails to select."""
    selected = list_of(source, "select")
    return [group for group in REQUIRED if group not in selected]


def main() -> int:
    with open(CONFIG, encoding="utf-8") as handle:
        source = handle.read()

    gone = missing(source)
    check("ruff-selects-every-required-group", not gone,
          "not selected: " + ", ".join(gone))

    # A group selected here and re-disabled in [lint] ignore is the same
    # deletion, one section further down.
    disabled = [group for group in REQUIRED if group in list_of(source, "ignore")]
    check("no-required-group-is-ignored", not disabled,
          "ignored: " + ", ".join(disabled))

    cap = re.search(r"^line-length\s*=\s*(\d+)\s*$", source, re.M)
    check("ruff-caps-line-length", cap is not None,
          "no top-level line-length in ruff.toml")

    floor = re.search(r'^target-version\s*=\s*"([^"]+)"\s*$', source, re.M)
    check("ruff-pins-target-version", floor is not None,
          "no top-level target-version in ruff.toml")

    # The gate and the config are one contract: the gate has to read this
    # file, or a stray config elsewhere decides what the mod is held to.
    with open(GATE, encoding="utf-8") as handle:
        gate_source = handle.read()
    check("lint-py-uses-the-shipped-config", "ruff.toml" in gate_source,
          "scripts/lint-py.sh does not name ruff.toml")

    # Negative control: a config missing one group is reported missing, so
    # the check above is known to be able to fail.
    short = missing('[lint]\nselect = ["E"]\n')
    check("detector-rejects-a-short-rule-set", tuple(short) == REQUIRED[1:],
          "a config selecting only E still counted as complete")

    return report()


if __name__ == "__main__":
    raise SystemExit(main())
