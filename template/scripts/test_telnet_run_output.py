#!/usr/bin/env python3
"""`run()` returns the command's output and none of the console's own noise.

`GameTelnet.run` is the only reason the telnet client exists: the client log
records that a command executed, while the console returns what it printed. The
game's console answers a command with a preamble around the answer — the echoed
command line, an "Executing command" notice, blank lines — and every oracle
check in the mod compares that output against an expected value, so noise left
in it fails checks against text nobody typed.

Driven over real sockets with a console that reproduces that preamble: the
question is what a caller receives, and a fake socket agrees with whichever
filter the client happens to have. The last case is a console that never
stops printing, for the collection window that must still end.
"""

from __future__ import annotations

import os
import socket
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import game_telnet
from gate import check
from gate import main as report

# Long enough that the reply is never read as a closed session mid-command,
# short enough that the gate costs one idle window rather than a poll loop.
SETTLE = 0.3


def console(listener: socket.socket) -> None:
    """One session: answer every command with the engine's own preamble.

    The connection is held open by blocking on the next recv rather than by a
    sleep, so the test costs one settle window and the session ends as soon as
    the client's farewell arrives.
    """
    try:
        connection, _ = listener.accept()
    except OSError:
        return
    with connection:
        while True:
            try:
                data = connection.recv(4096)
            except OSError:
                return
            if not data or b"exit" in data:
                return
            command = data.decode("utf-8", "replace").strip()
            try:
                connection.sendall(("\r\n" + command + "\r\n"
                                    + "Executing command " + command + "\r\n"
                                    + "\r\n"
                                    + "Spawn count: 3\r\n"
                                    + "\r\n"
                                    + "EntityID: 42\r\n").encode("utf-8"))
            except OSError:
                return


def endless_console(connection: socket.socket) -> None:
    """A console with no end to its output, until the client hangs up."""
    while True:
        try:
            connection.sendall(b"tick\r\n")
        except OSError:
            return


def ask(command: str) -> str:
    """`GameTelnet.run` for `command` against a fresh fake console."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    server = threading.Thread(target=console, args=(listener,), daemon=True)
    server.start()
    telnet = game_telnet.GameTelnet("127.0.0.1", listener.getsockname()[1], timeout=5.0)
    telnet._sock = socket.create_connection(("127.0.0.1", listener.getsockname()[1]),
                                            timeout=5.0)
    try:
        return telnet.run(command, settle=SETTLE)
    finally:
        telnet.close()
        listener.close()
        server.join(timeout=5)


def endless_console_returns() -> tuple[bool, str]:
    """(ok, detail) for a console that never stops printing.

    The window `_drain` collects over is extended by every chunk, so a console
    that keeps printing refreshed it forever and `run` never returned: the
    oracle session hung on a stream that was never going to stop. The
    collection is bounded by DRAIN_TOTAL_CAP_SECONDS, lowered here so the
    bound is what the gate measures rather than the half-minute it ships as.
    """
    shipped = game_telnet.DRAIN_TOTAL_CAP_SECONDS
    game_telnet.DRAIN_TOTAL_CAP_SECONDS = 0.4
    left, right = socket.socketpair()
    client = game_telnet.GameTelnet()
    client._sock = right
    printing = threading.Thread(target=endless_console, args=(left,), daemon=True)
    printing.start()
    try:
        client.send_raw("giveself")
        output = client._drain(0.1)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        game_telnet.DRAIN_TOTAL_CAP_SECONDS = shipped
        printing.join(timeout=5)
        client._sock = None
        left.close()
        right.close()
    if not output:
        return False, "the bounded collection returned nothing"
    return True, ""


def main() -> int:
    output = ask("giveself")

    check("the echoed command line is not part of the output",
          "giveself" not in output, repr(output))
    check("the console's own 'Executing command' notice is not part of the output",
          "Executing command" not in output, repr(output))
    check("every printed line of the answer survives",
          output == "Spawn count: 3\nEntityID: 42", repr(output))
    check("no blank line or trailing carriage return reaches the caller",
          "\r" not in output and "" not in output.split("\n"), repr(output))

    ok, detail = endless_console_returns()
    check("a console that never stops printing still ends the collection", ok, detail)

    return report()


if __name__ == "__main__":
    sys.exit(main())
