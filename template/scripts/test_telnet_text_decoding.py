#!/usr/bin/env python3
"""Console text must survive a recv() boundary that splits a character.

TCP is a byte stream, so a multi-byte UTF-8 character can land half in one
`recv()` and half in the next. The client decoded each chunk on its own, which
replaced both halves with U+FFFD: one non-ASCII character anywhere in a
command's output came back corrupted, and the playtest checks read exactly
that text. Bytes C3 A9 are `é`; delivered as two chunks they read as `�`
and `�`.

Driven over real sockets, not a stub: the question is what the wire hands
back and what `_recv` returns, and a fake socket agrees with either decoder.
The split is placed by the test, one chunk per `_recv`, so it lands
mid-character on every run.
"""

from __future__ import annotations

import os
import socket
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from game_telnet import READY_MARKERS, GameTelnet

LINE = "café \U0001F9F9 naïve"
BANNER = b"Pr\xc3\xa9t. " + READY_MARKERS[0].encode() + b"\r\n"
FLAGS = "\U0001F1E9\U0001F1EA"
# Half a character left behind by a session that was closed before the rest
# of it arrived.
STALE = b"\xc3"

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print("PASS " + name)
        return
    FAILURES.append(name)
    print("FAIL " + name + (": " + detail if detail else ""), file=sys.stderr)


def split_at(data: bytes, index: int) -> str:
    """`data` through `_recv`, one recv per half, split before `index`."""
    left, right = socket.socketpair()
    telnet = GameTelnet()
    telnet._sock = right
    try:
        left.sendall(data[:index])
        seen = telnet._recv()
        left.sendall(data[index:])
        return seen + telnet._recv()
    finally:
        telnet._sock = None
        left.close()
        right.close()


def fake_console(listener: socket.socket) -> None:
    """One session: the ready banner, then `Prêt` for every command."""
    try:
        connection, _ = listener.accept()
    except OSError:
        return
    with connection:
        connection.sendall(BANNER)
        while True:
            try:
                data = connection.recv(4096)
            except OSError:
                return
            if not data or b"exit" in data:
                return
            connection.sendall("\r\nPrêt\r\n".encode())


def reopened_session() -> tuple[bool, str]:
    """(ok, detail) for a console run that follows a half-read session."""
    left, right = socket.socketpair()
    telnet = GameTelnet()
    telnet._sock = right
    left.sendall(STALE)
    telnet._recv()          # held as an incomplete sequence, never as text
    telnet.close()
    left.close()
    right.close()

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    server = threading.Thread(target=fake_console, args=(listener,), daemon=True)
    server.start()
    telnet = GameTelnet("127.0.0.1", listener.getsockname()[1], timeout=5.0)
    try:
        telnet.connect()
        output = telnet.run("help", settle=0.3)
    except Exception as exc:  # escaping to here is the defect
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        telnet.close()
        listener.close()
        server.join(timeout=5)
    return output == "Prêt", repr(output)


def main() -> int:
    line = LINE.encode()
    check("a character split across two recvs is one character, not two U+FFFD",
          split_at(line, line.index(b"\xc3\xa9") + 1) == LINE,
          repr(split_at(line, line.index(b"\xc3\xa9") + 1)))

    flags = FLAGS.encode()
    check("a character split inside the astral plane is not corrupted",
          split_at(flags, 6) == FLAGS, repr(split_at(flags, 6)))

    check("bytes that are not UTF-8 still decode to U+FFFD",
          split_at(b"caf\xe9!\r\n", 1) == "caf\ufffd!\r\n",
          repr(split_at(b"caf\xe9!\r\n", 1)))

    ok, detail = reopened_session()
    check("a new session does not open with the previous one's partial character",
          ok, detail)

    print(f"{len(FAILURES)} failures.")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
