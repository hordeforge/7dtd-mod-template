#!/usr/bin/env python3
"""Structure-aware fuzz over the console byte stream in lib/game_telnet.py.

The dedicated server's telnet console is the one channel in this repo where
input is not written by the mod author and not a file on disk: it is a byte
stream from another machine, decoded across `recv()` boundaries and reduced to
a command's output that the playtest checks then read. The decoder is
incremental because a multi-byte character can straddle any two boundaries,
and the reduction drops three kinds of line. Both are hand-written
arithmetic over bytes nobody controls, and a console under load prints player
names, paths and numbers, not a fixed banner.

No fuzzing engine is available on the host (atheris and hypothesis are
absent and nothing installs them here), so this builds the input grammar
directly: a transcript of the fragments a real console prints (the ready
banner, the echo, the `Executing command` notice, answers carrying
non-ASCII), the bytes that break a decoder (a truncated sequence, a lone
continuation byte, an overlong form, a surrogate, a code point above U+10FFFF,
a NUL), and the separators `str.splitlines()` wrongly treats as line ends
(NEL, LS, PS, VT, FF). Each transcript is then mutated by truncating it
anywhere and by re-chunking it at arbitrary cut points.

It asserts the properties a coverage-guided fuzzer cannot check on its own:

- **total** — neither the decode nor the reduction raises on any of it; a
  console that prints something odd must not take a check down with it;
- **chunked decode equals one-shot decode** — the same stream decoded in
  arbitrary `recv()`-sized pieces has to be the text `bytes.decode` gives,
  which is what the incremental decoder exists for and what a per-chunk
  decode silently lost;
- **the wire's own line ends** — the reduced output, split on "\\n", has to
  be exactly the lines an independent CR/LF/CRLF scanner finds, so a NEL or
  a LINE SEPARATOR inside a printed name can never cut a line, and no
  character is dropped or duplicated on the way.

Run length is fixed so the gate is deterministic; set TELNET_FUZZ_ITERS for
a longer soak.
"""

from __future__ import annotations

import os
import random
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from game_telnet import READY_MARKERS, GameTelnet, command_output

DEFAULT_ITERATIONS = 2000
SEED = 20260928
COMMANDS = ("help", "giveself 1 0 1", 'say "hello"', "lp;time", "ce", "shutdown")

# Text a console really prints: names with an accent, a CJK answer, an emoji
# with a skin-tone modifier (a four-byte sequence plus a modifier), a
# combining mark, a full-width stop, and markup a colourised console emits.
ANSWERS = (
    "Prêt.",
    "café naïve \U0001F9F9",
    "このモッドは動く。",
    "\U0001F468\U0001F3FD connected",
    "Dále Straße Ñu",
    "Executing command: help",
    "stack: /opt/7 Days To Die/7DaysToDieServer.x86_64",
    "players online: 3",
    "\x1b[0m\x1b[37m  \r",
    "",
    "   ",
    "\x00\x01\x02",
    "x" * 300,
)

# Separators that end a line in str.splitlines() and nowhere on this wire.
NOT_LINE_ENDS = ("\u0085", "\u2028", "\u2029", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e")

# Byte sequences that break a decoder: a truncated multi-byte tail, a lone
# continuation byte, an overlong NUL, a surrogate half, and a scalar above
# the Unicode range.
BAD_BYTES = (
    b"\xc3", b"\xe2\x82", b"\xf0\x9f\xa7", b"\x80", b"\xbf", b"\xc0\x80",
    b"\xe0\x80\x80", b"\xed\xa0\x80", b"\xf4\x90\x80\x80", b"\xf5\x80\x80\x80",
    b"\xff", b"\xfe\xff", b"\xc2", b"\xef\xbb\xbf", b"\xe2\x80\xa8",
)

# Bare CR, LF and CRLF: the only three that end a line on this wire.
WIRE_ENDS = (b"\r", b"\n", b"\r\n")


def transcript(rng: random.Random) -> tuple[bytes, str]:
    """A console session's bytes and the command it is answering."""
    command = rng.choice(COMMANDS)
    parts: list[bytes] = []
    for _ in range(rng.randint(1, 6)):
        roll = rng.random()
        if roll < 0.2:
            parts.append(READY_MARKERS[0].encode() + rng.choice(WIRE_ENDS))
        elif roll < 0.35:
            parts.append(command.encode() + rng.choice(WIRE_ENDS))
        elif roll < 0.5:
            parts.append(f"Executing command: {command}".encode() + rng.choice(WIRE_ENDS))
        elif roll < 0.65:
            parts.append(rng.choice(BAD_BYTES))
        else:
            line = rng.choice(ANSWERS)
            # A separator that is not one lands inside a printed name.
            if rng.random() < 0.4:
                cut = rng.randrange(len(line) + 1)
                line = line[:cut] + rng.choice(NOT_LINE_ENDS) + line[cut:]
            parts.append(line.encode("utf-8", "surrogatepass") + rng.choice(WIRE_ENDS))
    return b"".join(parts), command


def mutate(data: bytes, rng: random.Random) -> bytes:
    """The same stream, cut short and re-chunked the way TCP delivers it."""
    if data and rng.random() < 0.3:
        data = data[: rng.randrange(len(data))]
    return data


def read_off_the_wire(data: bytes) -> str:
    """`data` through the client's own `_recv`, one byte per read.

    One byte per `recv()` is the harshest split the wire can deliver: every
    multi-byte character in the stream is cut after its first byte, and the
    text still has to come back whole. The stream is written to a socket pair
    and read back through the real client object rather than through a copy
    of its decoder, so a `recv()` that decoded on its own instead of
    carrying the incomplete tail forward fails here.
    """
    left, right = socket.socketpair()
    telnet = GameTelnet()
    telnet._sock = right
    pieces: list[str] = []
    try:
        for index in range(len(data)):
            left.sendall(data[index:index + 1])
            pieces.append(telnet._recv())
        # A session that ends mid-character flushes the tail rather than
        # carrying it into the next connection.
        pieces.append(telnet._decoder.decode(b"", True))
    finally:
        telnet._sock = None
        left.close()
        right.close()
    return "".join(pieces)


def scan_lines(text: str) -> list[str]:
    """`text` split on CR, LF and CRLF only, by a scanner written here.

    Deliberately not the regex in game_telnet: the point of the comparison is
    two independent readings of the same rule agreeing.
    """
    lines: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\r":
            lines.append("".join(current))
            current = []
            if text[index + 1: index + 2] == "\n":
                index += 1
        elif char == "\n":
            lines.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    lines.append("".join(current))
    return lines


def expected_lines(raw: str, command: str) -> list[str]:
    """The lines a reader of the protocol says survive the reduction."""
    return [
        line.rstrip("\r") for line in scan_lines(raw)
        if line.strip() and line.strip() != command
        and "Executing command" not in line
    ]


def main() -> int:
    iterations = int(os.environ.get("TELNET_FUZZ_ITERS", DEFAULT_ITERATIONS))
    rng = random.Random(SEED)
    failures: list[str] = []

    def fail(kind: str, detail: str) -> None:
        if len(failures) < 5:
            failures.append(f"{kind}: {detail}")

    for _ in range(iterations):
        data, command = transcript(rng)
        data = mutate(data, rng)
        try:
            raw = read_off_the_wire(data)
        except Exception as exc:
            fail("read-off-the-wire", f"{type(exc).__name__}: {exc}")
            continue

        try:
            output = command_output(raw, command)
        except Exception as exc:
            fail("command_output", f"{type(exc).__name__}: {exc}")
            continue

        whole = data.decode("utf-8", "replace")
        if raw != whole:
            fail("chunked-decode", f"{data!r} read as {raw!r}, not {whole!r}")
            continue

        want = expected_lines(whole, command)
        got = output.split("\n") if output else []
        if got != want:
            fail("line-breaks", f"{data!r} reduced to {got!r}, expected {want!r}")

    if failures:
        for item in failures:
            print("FAIL " + item, file=sys.stderr)
        print(f"{len(failures)} fuzz failures over {iterations} iterations.",
              file=sys.stderr)
        return 1

    print(f"PASS telnet-stream fuzz: {iterations} iterations, every stream "
          "decoded whole and reduced on the wire's own line ends")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
