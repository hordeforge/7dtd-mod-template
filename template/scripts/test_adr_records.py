#!/usr/bin/env python3
"""Decision records hold their shape: an ADR is a decision, indexed, linked.

`docs/adr/README.md` states a lifecycle the mod's own agents have to keep:
zero-padded sequential numbers, `Status` on every record, a status vocabulary
of Accepted / Deprecated / Superseded by NNNN, a superseding record that
names the one it replaces, and one index row per record. `docs/design.md` and
`docs/architecture.md` state a second: decision-log headings carry a date
(`Decided YYYY-MM-DD: <topic>`). A reader trusts those files; a status
left at `Proposed`, a record missing from the index, or a supersession that
points at nothing makes a wrong accepted record look settled.

`docs/adr/template.md` is the skeleton new records are copied from, so the
skeleton itself is checked: a template the set has drifted away from is
copied, and every later record inherits the drift.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADR_DIR = os.path.join(MOD_DIR, "docs", "adr")
README = "README.md"
TEMPLATE = "template.md"
META = frozenset({README, TEMPLATE})

RECORD_NAME = re.compile(r"^(?P<number>[0-9]{4})-(?P<slug>[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\.md$")
DATED = re.compile(r"^Date: (?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})\s*$", re.MULTILINE)
STATUS_HEADING = re.compile(r"^## Status\s*$", re.MULTILINE)
STATUS_LINE = re.compile(r"^(?P<value>.+?)\s*$")
STATUS_ACCEPTED = re.compile(r"^Accepted$")
STATUS_DEPRECATED = re.compile(r"^Deprecated$")
STATUS_SUPERSEDES = re.compile(
    r"^Superseded by \[?(?P<target>[0-9]{4})\]?(?:\((?P<link>[^)]+)\))?$")
INDEX_ROW = re.compile(
    r"^\|\s*(?P<number>[0-9]{4})\s*\|(?P<title>[^|]*)\|(?P<status>[^|]*)\|\s*$", re.MULTILINE)
LOG_HEADING = re.compile(r"^## (?P<title>.+?)\s*$", re.MULTILINE)
DATED_LOG_HEADING = re.compile(r"^(?:Decided|Resolved) [0-9]{4}-[0-9]{2}-[0-9]{2}: .+$")
LOG_ENTRY_HINT = re.compile(r"^(?:Decided|Resolved)\b|\b[0-9]{4}-[0-9]{2}-[0-9]{2}\b")
REQUIRED_SECTIONS = ("## Context", "## Decision", "## Consequences")
TEMPLATE_MARKERS = ("# NNNN. Title", "Date: YYYY-MM-DD", "Accepted | Deprecated")
PROPOSED = re.compile(r"\bproposed\b", re.IGNORECASE)


def read(path: str) -> str:
    with open(path, encoding="utf-8-sig") as handle:
        return handle.read()


def record_number(filename: str) -> int | None:
    """The number a record filename carries, or None when the name is off-convention."""
    match = RECORD_NAME.match(filename)
    return int(match["number"]) if match else None


def status_of(text: str) -> str | None:
    """The `## Status` value of a record, or None when there is no such section."""
    match = STATUS_HEADING.search(text)
    if match is None:
        return None
    for line in text[match.end():].splitlines():
        stripped = line.strip()
        if stripped:
            value = STATUS_LINE.match(stripped)
            return value["value"] if value else None
    return None


def index_of(text: str) -> tuple[dict[int, str], list[int]]:
    """The ADR index as ({number: status cell}, numbers with a second row).

    The header and rule rows carry no number, so they do not match. A number
    listed twice is a second row for one record, not a second record: it
    collapses into the same key here, so the duplicate is reported alongside
    rather than lost.
    """
    cells: dict[int, list[str]] = {}
    for match in INDEX_ROW.finditer(text):
        cells.setdefault(int(match["number"]), []).append(match["status"].strip())
    duplicated = sorted(number for number, values in cells.items() if len(values) > 1)
    return {number: values[0] for number, values in cells.items()}, duplicated


def normalized_status(status: str) -> str:
    """A record's status as the index writes it, link syntax dropped."""
    supersedes = STATUS_SUPERSEDES.match(status)
    return f"Superseded by {supersedes['target']}" if supersedes else status


def audit_records(records: dict[str, str], index_text: str) -> list[str]:
    """Every way the ADR set can contradict README.md's stated lifecycle."""
    problems: list[str] = []
    numbers = {record_number(name): name for name in records}
    indexed, duplicated = index_of(index_text)
    for number in duplicated:
        problems.append(f"{README}: {number} has more than one index row")
    for name, text in sorted(records.items()):
        for section in REQUIRED_SECTIONS:
            if f"\n{section}\n" not in text:
                problems.append(f"{name}: no '{section}' section")
        if DATED.search(text) is None:
            problems.append(f"{name}: no 'Date: YYYY-MM-DD' line")
        status = status_of(text)
        if status is None:
            problems.append(f"{name}: no '## Status' value")
        elif PROPOSED.search(status):
            problems.append(f"{name}: an ADR is a decision made, status is '{status}'")
        elif not (
            STATUS_ACCEPTED.match(status)
            or STATUS_DEPRECATED.match(status)
            or STATUS_SUPERSEDES.match(status)
        ):
            problems.append(f"{name}: status '{status}' is outside the vocabulary")
        supersedes = STATUS_SUPERSEDES.match(status or "")
        if supersedes:
            successor = numbers.get(int(supersedes["target"]))
            if successor is None:
                problems.append(f"{name}: superseded by {supersedes['target']}, no such record")
            else:
                if supersedes["link"] is not None and supersedes["link"] != successor:
                    problems.append(f"{name}: supersession link names {supersedes['link']}")
                number = f"{record_number(name):04d}"
                if not re.search(rf"(?<![0-9]){number}(?![0-9])", records[successor]):
                    problems.append(f"{successor}: does not name the {name} record it replaces")
        if record_number(name) not in indexed:
            problems.append(f"{name}: not in the index in {README}")
        elif status is not None and indexed[record_number(name)] != normalized_status(status):
            problems.append(
                f"{name}: index says '{indexed[record_number(name)]}', record says '{status}'")
    for number in sorted(indexed):
        if number not in numbers:
            problems.append(f"{README}: index lists {number}, no such record")
    ordered = sorted(n for n in numbers if n is not None)
    if ordered != list(range(1, len(ordered) + 1)):
        problems.append(f"numbers {ordered} are not sequential from 0001")
    return problems


def audit_log(text: str, filename: str) -> list[str]:
    """Decision-log entries that do not read `Decided YYYY-MM-DD: <topic>`."""
    problems = []
    for match in LOG_HEADING.finditer(text):
        title = match["title"]
        if DATED_LOG_HEADING.match(title) or LOG_ENTRY_HINT.search(title) is None:
            continue
        problems.append(f"{filename}: '## {title}' is not a dated Decided/Resolved entry")
    return problems


SKELETON = "## Context\n\nx\n\n## Decision\n\ny\n\n## Consequences\n\nz\n"
GOOD = {
    "0001-use-a-logger.md": "# 0001. Use a logger\n\nDate: 2026-01-02\n\n"
    "## Status\n\nAccepted\n\n" + SKELETON,
    "0002-drop-the-parser.md": "# 0002. Drop the parser\n\nDate: 2026-01-03\n\n"
    "## Status\n\nSuperseded by [0003](0003-adopt-the-parser.md)\n\n" + SKELETON,
    "0003-adopt-the-parser.md": "# 0003. Adopt the parser\n\nDate: 2026-01-04\n\n"
    "## Status\n\nAccepted\n\n## Context\n\nReplaces 0002.\n\n"
    "## Decision\n\ny\n\n## Consequences\n\nz\n",
}
INDEX = ("## Index\n\n| # | Title | Status |\n|---|---|---|\n"
         "| 0001 | Use a logger | Accepted |\n"
         "| 0002 | Drop the parser | Superseded by 0003 |\n"
         "| 0003 | Adopt the parser | Accepted |\n")


def variant(records: dict[str, str], name: str, old: str, new: str) -> dict[str, str]:
    """One record's text changed, the rest of the set left alone."""
    return {**records, name: records[name].replace(old, new)}


def control(name: str, records: dict[str, str], index: str, needle: str) -> None:
    problems = audit_records(records, index)
    check(f"negative control: {name}",
          any(needle in problem for problem in problems), repr(problems))


def main() -> int:
    check("negative control: a well-kept set passes", audit_records(GOOD, INDEX) == [],
          repr(audit_records(GOOD, INDEX)))
    control("a proposed ADR fails", variant(GOOD, "0003-adopt-the-parser.md",
          "Accepted", "Proposed"), INDEX, "an ADR is a decision made")
    control("a supersession pointing nowhere fails", variant(GOOD, "0002-drop-the-parser.md",
          "0003", "0009"), INDEX, "no such record")
    control("a record missing from the index fails", GOOD,
          INDEX.replace("| 0002 | Drop the parser | Superseded by 0003 |\n", ""),
          "not in the index")
    control("a record with two index rows fails", GOOD,
            INDEX.replace("| 0001 | Use a logger | Accepted |\n",
                          "| 0001 | Use a logger | Accepted |\n"
                          "| 0001 | Use a logger | Accepted |\n"),
            "more than one index row")
    control("an index status that drifted from the record fails", GOOD,
          INDEX.replace("Superseded by 0003 |", "Accepted |"), "index says")
    control("a numbering gap fails", {"0002-drop-the-parser.md": GOOD["0002-drop-the-parser.md"]},
          INDEX, "sequential")

    dated_log = "## Decisions\n\n## Decided 2026-01-02: pick a logger\n\n## Item balance\n"
    check("negative control: a dated decision-log entry passes",
          audit_log(dated_log, "design.md") == [], repr(audit_log(dated_log, "design.md")))
    undated = dated_log.replace("Decided 2026-01-02: pick a logger", "Decided: pick a logger")
    check("negative control: an undated decision-log entry fails",
          bool(audit_log(undated, "design.md")), repr(audit_log(undated, "design.md")))

    present = sorted(name for name in os.listdir(ADR_DIR)
                     if name.endswith(".md") and name not in META)
    records = {name: read(os.path.join(ADR_DIR, name)) for name in present}
    off_convention = [name for name in records if record_number(name) is None]
    check("every record in docs/adr follows NNNN-title.md", not off_convention,
          repr(off_convention))
    problems = audit_records(records, read(os.path.join(ADR_DIR, README)))
    check("the ADR set matches the lifecycle in docs/adr/README.md", not problems,
          "; ".join(problems))

    template = read(os.path.join(ADR_DIR, TEMPLATE))
    missing_markers = [marker for marker in TEMPLATE_MARKERS if marker not in template]
    check("docs/adr/template.md still carries the skeleton", not missing_markers,
          repr(missing_markers))

    for log in ("design.md", "architecture.md"):
        log_problems = audit_log(read(os.path.join(MOD_DIR, "docs", log)), log)
        check(f"docs/{log} decision headings are dated entries", not log_problems,
              "; ".join(log_problems))
    return report()


if __name__ == "__main__":
    sys.exit(main())
