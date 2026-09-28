#!/usr/bin/env python3
"""The telnet client must not accumulate the session's console output.

`scripts/lib/game_telnet.py` lives for the length of an oracle session, which
can be hundreds of `run()` calls. A field that concatenates every chunk the
client ever drained grows with the session, is never read, and a long session
then carries the whole transcript in memory: a playtest run that saves, spawns
and inspects the world prints a lot. Output belongs to the call that asked for
it (`_drain` returns it), so the client keeps none.

Over a real socket pair, so the question is what a session's traffic does to
the client's state rather than what a stub is handed.
"""

from __future__ import annotations

import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from game_telnet import GameTelnet
from gate import check
from gate import main as report

CHUNK = "x" * 4096 + "\r\n"
COMMANDS = 20


def session_state() -> tuple[bool, str]:
    """(ok, detail) after driving COMMANDS commands through a console."""
    left, right = socket.socketpair()
    client = GameTelnet()
    client._sock = right
    try:
        left.sendall(CHUNK.encode())
        client._drain(0.05)
        for _ in range(COMMANDS):
            left.sendall(CHUNK.encode())
            client._drain(0.05)
    except OSError as exc:
        return False, repr(exc)
    finally:
        client._sock = None
        left.close()
        right.close()

    # No instance state grows with the session's output: the decoded-text
    # accumulator that did is gone, and the decoder carries only the
    # incomplete tail of the last chunk, so its buffer stays at zero.
    decoder_state = vars(client._decoder).get("buffer", b"")
    retained = [name for name, value in vars(client).items()
                if isinstance(value, str) and len(value) > 1024]
    if retained:
        return False, "retains " + ", ".join(
            f"{name} ({len(getattr(client, name))} chars)" for name in retained)
    if decoder_state:
        return False, f"decoder holds {len(decoder_state)} undecoded bytes"
    return True, ""


def main() -> int:
    ok, detail = session_state()
    check("a long session retains no console output", ok, detail)
    return report()


if __name__ == "__main__":
    sys.exit(main())
