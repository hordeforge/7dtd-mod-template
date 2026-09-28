#!/usr/bin/env python3
"""Substitute a scaffolded mod's tokens and strip the blocks that do not apply.

Called by `new-mod.sh` as `substitute-tokens.py MOD_DIR`; every other input
arrives in the environment:

    ANVIL_NAME  ANVIL_DISPLAY  ANVIL_AUTHOR  ANVIL_PURPOSE
    ANVIL_SKIP_EAC  ANVIL_CSHARP  ANVIL_ASSETS

`MOD_DIR` is the staged copy of `template/` the scaffolder built. Every text
file under it is rewritten with the placeholder tokens replaced and the
optional-feature marker blocks removed. Exits 2 on a config value the user has
to fix, 1 on a file it cannot read.
"""

from __future__ import annotations

import datetime
import html
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

mod_dir = sys.argv[1]

def from_shell(name: str) -> str:
    """A value the shell exported, as text this program can write back out.

    A shell variable is a byte string, and `os.environ` decodes one that is
    not UTF-8 with `surrogateescape`, so a `newmod.conf` holding `author=Jos<e9>`
    in latin-1 (any editor still saving that encoding) arrived here as
    'Jos<udce9>'. Every write below is `encoding="utf-8"`, so the substituted
    token raised UnicodeEncodeError out of the scaffolder with a traceback and
    no mod, over a name the user had typed.

    The bytes go back through `surrogateescape` and are then decoded as UTF-8
    with `replace`: text that was already UTF-8 comes back unchanged, and a
    byte that is not becomes U+FFFD, which is a substitution a reader can see
    rather than a crash. The modlet is never handed a lone surrogate.
    """
    raw = os.environ[name]
    return raw.encode("utf-8", "surrogateescape").decode("utf-8", "replace")

# Characters that draw nothing and, worse, reorder what sits around them: the
# bidi overrides and isolates, the soft hyphen, the zero-width space, the word
# joiner, the BOM, and any control character. A display name or an author
# carrying one is a second string that reads as the first, and those two
# fields are how a player tells one mod from another, so the run stops rather
# than seed a look-alike into the mod browser. The zero-width joiner and
# non-joiner are not in this set: they are how an emoji sequence and a
# Persian word are written, and they attach to a neighbouring character
# rather than reorder the line.
INVISIBLE = frozenset(
    "\u00ad\u200b\u2060\ufeff"
    "\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
    "\u2066\u2067\u2068\u2069")

def readable(label: str, text: str) -> str:
    """`text` as the config reader saw it, or exit 2 naming what is in it.

    Exit 2 is the config's own status: a name carrying a character that draws
    nothing is a value the user has to fix, not a step that failed part way.
    """
    found = sorted({char for char in text
                    if char in INVISIBLE or unicodedata.category(char) == "Cc"})
    if found:
        listed = ", ".join(f"U+{ord(char):04X}" for char in found)
        print(f"ERROR: {label} in the config holds a character that draws nothing: {listed}.",
              file=sys.stderr)
        print("       A mod name that is not the name a player reads is not this mod's name.",
              file=sys.stderr)
        raise SystemExit(2)
    return text

# A substituted value has to survive the grammar of every file it lands
# in, and those grammars are not the same.
FORBIDDEN_IN_XML = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f\uFFFE\uFFFF]"
    "|[\uD800-\uDFFF\uFDD0-\uFDEF]")
LINE_BREAKS = re.compile("[\r\n\u0085\u2028\u2029]")
WHITESPACE_RUN = re.compile(r"\s+")


def one_line(value: str) -> str:
    """`value` as the single line of text a substituted token has to be.

    The tokens land in an XML attribute, a C# string literal, a markdown
    heading and a TOML comment, and all four read a line break as the end
    of what they were reading: a display name that came in over two lines
    wrote a ModInfo.xml whose second line is not XML at all, a README
    whose first heading stops mid-name, and a settings file the DLL
    rejects. The control characters and lone surrogates here are worse
    still, because XML 1.0 has no production for one: the game cannot
    load the file the run reported as written.

    NFC so the same name typed on a Mac (which composes) and on Windows
    (which often does not) scaffolds the same bytes, rather than a diff
    that shows only that the keyboard layout differed.
    """
    value = FORBIDDEN_IN_XML.sub("", value)
    value = LINE_BREAKS.sub(" ", value)
    return WHITESPACE_RUN.sub(" ", unicodedata.normalize("NFC", value)).strip()


def csharp_escape(value: str) -> str:
    """`value` as the contents of a C# string literal.

    `ConsoleCmd.getDescription()` returns `"__MOD_DISPLAY_NAME__
    settings"`, so a display name holding a quote or a backslash closes
    the literal and leaves a file the compiler rejects: the scaffolder
    reports success and the mod's first build fails, over the author's
    own display name. An apostrophe, a pasted straight quote, and a
    backtick off a Cyrillic or Greek layout all reach here. The backslash
    goes first, so the escapes added for the quote are not escaped again.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


# One line of text first, so what readable() checks is what is written: the
# characters that draw nothing survive that pass, and they are the ones a
# reader cannot see.
purpose = readable("purpose", one_line(from_shell("ANVIL_PURPOSE")))
display = readable("display_name", one_line(from_shell("ANVIL_DISPLAY")))
the_author = readable("author", one_line(from_shell("ANVIL_AUTHOR")))
# ModInfo.xml is the mod's single source of truth for its version: the game
# reads that field and nothing else, and the release readme's first line has
# to name the same version. Reading it here keeps the two in step at scaffold
# time; the static-check gate keeps them in step afterwards.
version = ""
for field in ET.parse(os.path.join(mod_dir, "ModInfo.xml")).getroot():
    if field.tag == "Version":
        version = (field.get("value") or "").strip()
if not version:
    sys.exit("ERROR: ModInfo.xml has no Version value; the mod's version is undeclared.")

ZWJ = "\u200d"
# A code point that can only follow another one: a zero-width joiner or space,
# a BOM, a variation selector, an emoji skin-tone modifier, or a mark in any
# script (a combining accent, a Devanagari matra, a Thai vowel sign, a
# keycap's enclosing mark). Cutting the description between one of these and
# the character it belongs to leaves it stranded, and ModInfo.xml's
# Description is rendered by the game, so the truncation has to end on a whole
# character.
#
# The mark test is the Unicode property, not a list of ranges: a list of
# combining marks needs an entry per script, and every script left out of it
# truncates mid-word. Marks are the Mn, Mc and Me categories, and the ranges
# below are the non-marks that attach the same way.
ATTACHING = re.compile("[\u200d\u200c\ufeff\ufe00-\ufe0f\ufe20-\ufe2f"
                       "\U0001f3fb-\U0001f3ff]")
REGIONAL_INDICATOR = (0x1F1E6, 0x1F1FF)

def attaches(char: str) -> bool:
    """Whether `char` belongs to the character before it, not after it."""
    if ATTACHING.match(char):
        return True
    return unicodedata.category(char) in ("Mn", "Mc", "Me")

def ends_mid_cluster(text: str) -> bool:
    """Whether `text` stops inside a character, so a cut there strands half of one.

    Three ways a fixed code-point limit lands inside one: on a mark, on the
    base of a ZWJ sequence whose joiner is already behind it, and on the
    first of a flag's two regional indicators.
    """
    if not text:
        return False
    if attaches(text[-1]):
        return True
    if len(text) > 1 and text[-2] == ZWJ:
        return True
    run = 0
    for char in reversed(text):
        if REGIONAL_INDICATOR[0] <= ord(char) <= REGIONAL_INDICATOR[1]:
            run += 1
        else:
            break
    return run % 2 == 1

def to_clusters(text: str, limit: int) -> str:
    """`text` cut to at most `limit` code points, ending on a whole character."""
    cut = text[:limit]
    while cut and ends_mid_cluster(cut):
        cut = cut[:-1]
    return cut

# Where a sentence ends, per script. A Latin sentence closes on `.`, `!` or
# `?` and writes whitespace or nothing after it; a CJK, Devanagari, Khmer,
# Mongolian, Ethiopic, Burmese or Tibetan one closes on its own stop
# character and writes nothing after it at all, so an ASCII-only rule reads
# a Japanese purpose as one long sentence and leaves the mod browser's
# description holding two of them, cut mid-phrase. The same holds for every
# other script that owns a stop: Armenian, Greek (whose question mark is
# U+037E, a glyph that reads as a semicolon), Persian and Arabic.
ASCII_STOP = ".!?"
OTHER_STOP = "。！？．｡؟۔।॥።᠃᠉။ႁႂႃႄႅႆႇႈႉႊႋႌႍႎႏ។៕៿։፡؛།༎"  # noqa: RUF001 each look-alike is a real sentence stop of its script


def first_sentence(text: str) -> str:
    """`text` up to its first sentence end, or all of it when it has none.

    A stop is not an end where a digit (`v1.2`) or a lone capital (the `J.` of
    an initial) ends the word before it, and an ASCII stop is one only where
    whitespace or the end of the text follows it. The unit is the last word,
    not the whole prefix: `J` alone in "A mod about J. R. R. Tolkien" is an
    initial, while a single-character *prefix* is only the first word of the
    purpose, so measuring the prefix cut the description at the first
    middle initial and left the browser showing "A mod about J.".
    """
    for index, char in enumerate(text):
        if char not in ASCII_STOP + OTHER_STOP:
            continue
        if char in ASCII_STOP and index + 1 < len(text) and not text[index + 1].isspace():
            continue
        words = text[:index].split()
        if words and char in ASCII_STOP:
            # The last character, not the whole word: `v1.2` ends the word in
            # a digit while the word itself is `v1`, and a plain isdigit() on
            # it never fires.
            word = words[-1]
            if word[-1].isdigit() or (word.isupper() and len(word) == 1):
                continue
        return text[:index + 1]
    return text

# The description is the mod browser's one line: 200 code points, whatever
# the script, not bytes and not grapheme clusters, and the cut lands on a
# whole character in that script.
DESCRIPTION_LIMIT = 200
short = to_clusters(first_sentence(purpose), DESCRIPTION_LIMIT)

# The author token names the Harmony id, a lowercase ASCII string. Decomposing
# first turns an accented name into its base letters, so Müller and its
# decomposed spelling both reduce to muller rather than mller. Folding rather
# than lowering is what keeps one author's name from reaching another's id:
# lower() maps a German ß to nothing, so "Weiß" and "Wei" both reduced to
# "wei", and two different authors were given one Harmony id.
author_id = re.sub(r"[^a-z0-9]", "",
                   unicodedata.normalize("NFKD", the_author).casefold())
tokens = {
    "__MOD_NAME__": one_line(from_shell("ANVIL_NAME")),
    "__MOD_NAME_LOWER__": one_line(from_shell("ANVIL_NAME")).lower(),
    "__MOD_DISPLAY_NAME__": display,
    "__MOD_AUTHOR__": the_author,
    "__MOD_AUTHOR_LOWER__": author_id or "author",
    "__MOD_PURPOSE__": purpose,
    "__MOD_PURPOSE_SHORT__": short,
    "__MOD_VERSION__": version,
    # The date this mod's first release section carries. A changelog entry
    # with no date is a version a reader cannot place in time, and the one
    # every mod starts with is the one a mod author copies when they cut
    # their next release.
    "__MOD_RELEASE_DATE__": datetime.date.today().isoformat(),  # noqa: DTZ011 the author's local calendar date
    "__SKIP_WITH_ANTI_CHEAT__": one_line(from_shell("ANVIL_SKIP_EAC")),
}
xml_tokens = {token: html.escape(value, quote=True)
              for token, value in tokens.items()}
cs_tokens = {token: csharp_escape(value)
             for token, value in tokens.items()}

CSHARP = ("<!-- ANVIL:CSHARP-BEGIN -->", "<!-- ANVIL:CSHARP-END -->")
ASSETS_MAKE = ("# ANVIL:ASSETS-BEGIN", "# ANVIL:ASSETS-END")
ASSETS_HTML = ("<!-- ANVIL:ASSETS-BEGIN -->", "<!-- ANVIL:ASSETS-END -->")
# file -> {marker pair: the feature it documents}. A block whose feature is off
# loses everything between the markers, so neither the Makefile nor the prose
# names a target that is gone; the two marker lines go either way. A pair may
# appear more than once in one file: the Makefile marks the asset help text
# and the asset .PHONY line separately.
marked = {
    "Makefile": {ASSETS_MAKE: "assets"},
    "README.md": {CSHARP: "csharp"},
    "AGENTS.md": {CSHARP: "csharp", ASSETS_HTML: "assets"},
}

def strip_marked(text: str, blocks: dict[tuple[str, str], str]) -> str:
    """Take the marker lines out of `text`, and a block whose feature is off.

    One pass over the lines, whatever the blocks: a marker opens a block and
    the next marker of the same pair closes it, and a block never closed runs
    to the end of the file. A block whose feature is on is entered too, and
    only its content kept, or its closing marker would survive into the mod.
    Both are whole-line matches, so a marker inside a paragraph of prose is
    not one.
    """
    drop_when_off = {markers[0]: os.environ["ANVIL_" + feature.upper()] != "yes"
                     for markers, feature in blocks.items()}
    closers = {markers[1] for markers in blocks}
    kept, inside, dropping = [], False, False
    for line in text.splitlines(keepends=True):
        marker = line.strip()
        if not inside and marker in drop_when_off:
            inside, dropping = True, drop_when_off[marker]
        elif inside and marker in closers:
            inside = dropping = False
        elif not inside or not dropping:
            kept.append(line)
    return "".join(kept)

for base, dirs, files in os.walk(mod_dir):
    dirs[:] = [d for d in dirs if d != ".git"]
    for f in files:
        path = os.path.join(base, f)
        try:
            # newline="" on both ends: a CRLF source file must survive the
            # round trip byte for byte, and an LF file must not be rewritten
            # to CRLF by a Windows scaffolder.
            with open(path, encoding="utf-8", newline="") as handle:
                text = handle.read()
        except UnicodeDecodeError:
            # A binary asset ships verbatim and has no token in it. Anything
            # else is not a substitute for a failure: an unreadable file
            # fails the run rather than shipping with its tokens in place.
            continue
        except OSError as exc:
            print(f"ERROR: could not read {path}: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        out = strip_marked(text, marked[f]) if base == mod_dir and f in marked else text
        # Two of these files take a value as syntax rather than as text.
        # ModInfo.xml's land in an XML attribute, where a bare `&`, `<` or
        # `"` ends the attribute and leaves the file the game cannot parse.
        # A C# file's land in a string literal, where a bare `"` or `\` ends
        # it and leaves a file the compiler rejects. Every other consumer (a
        # markdown file, a TOML comment) takes the text as it stands.
        if base == mod_dir and f == "ModInfo.xml":
            here = xml_tokens
        elif f.endswith(".cs"):
            here = cs_tokens
        else:
            here = tokens
        for token, value in here.items():
            out = out.replace(token, value)
        if out != text:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(out)
