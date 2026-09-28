#!/usr/bin/env python3
"""A telnet read has to end, and keep only as much as it was asked to.

`_drain` waits for the console to go quiet, which is not the same as waiting
for a fixed time: the window moves forward with every chunk, so a server that
prints without stopping (a world save reporting progress, a command that logs
as it runs) pushed it forward forever, and the buffer it was building grew for
as long as the server kept talking. The read now has an absolute end and the
buffer a cap, and both are properties a caller depends on: a check that oracles
against a chatty server hung instead of reporting.

No game and no server: the console is a local socket answering with as much as
it is told to.
"""

from __future__ import annotations

import contextlib
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import game_telnet
from gate import check
from gate import main as report

# The ceiling this gate runs against. Short enough that a runaway read fails
# the gate instead of holding it open, and long enough that the loop is driven
# by the chatty server rather than by the ceiling on its own.
FAST_CEILING_SECONDS = 1.0
# Longer than the ceiling, so a drain that ends is one the ceiling ended.
LONG_SETTLE_SECONDS = 5.0
# The read itself runs under this. A drain with no ceiling does not return, and
# a gate that waits on it is a gate that wedges `make test` rather than failing
# it: the defect under test is the one thing here that can hang.
WATCHDOG_SECONDS = 10.0


def flooding_console(listener: socket.socket) -> None:
    """One session that never stops talking."""
    with contextlib.suppress(OSError):
        connection, _ = listener.accept()
    with connection:
        with contextlib.suppress(OSError):
            connection.sendall(game_telnet.READY_MARKERS[0].encode() + b"\r\n")
        # The server never reads its own backlog, so it fills the client's
        # receive window and blocks: the client keeps draining what already
        # arrived, and the server is free to keep printing.
        while True:
            try:
                connection.sendall(b"log line of output\r\n" * 512)
            except OSError:
                return


def chatty(command: str) -> tuple[str, float]:
    """`GameTelnet.run` against a console that never goes quiet."""
    with contextlib.ExitStack() as stack:
        listener = stack.enter_context(contextlib.closing(socket.socket()))
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        server = threading.Thread(target=flooding_console, args=(listener,), daemon=True)
        server.start()
        stack.callback(server.join, 5)
        telnet = game_telnet.GameTelnet("127.0.0.1", listener.getsockname()[1], timeout=5.0)
        stack.callback(telnet.close)
        telnet.connect()
        started = time.monotonic()
        output = telnet.run(command, settle=LONG_SETTLE_SECONDS)
        return output, time.monotonic() - started


def chatty_under_watchdog() -> tuple[str | None, float]:
    """`chatty`'s result, or (None, WATCHDOG_SECONDS) if the read never ended.

    The read is a daemon thread so the gate still exits: the whole point is
    that a missing ceiling shows up as a failed gate, not as a run that has to
    be killed. Its sockets go with the process.
    """
    result: list[tuple[str, float]] = []
    started = time.monotonic()
    worker = threading.Thread(
        target=lambda: result.append(chatty("giveself")), daemon=True)
    worker.start()
    worker.join(WATCHDOG_SECONDS)
    if not result:
        return None, time.monotonic() - started
    return result[0]


def rejects_bad_timeout(timeout: float) -> bool:
    """`connect` refuses a non-positive timeout with no socket acquired."""
    telnet = game_telnet.GameTelnet("127.0.0.1", 1, timeout=timeout)
    try:
        telnet.connect(wait=0.1)
    except ValueError:
        return telnet._sock is None
    except Exception:
        return False
    finally:
        telnet.close()
    return False


def main() -> int:
    ceiling = game_telnet.DRAIN_MAX_TOTAL_SECONDS
    game_telnet.DRAIN_MAX_TOTAL_SECONDS = FAST_CEILING_SECONDS
    try:
        output, elapsed = chatty_under_watchdog()
    finally:
        game_telnet.DRAIN_MAX_TOTAL_SECONDS = ceiling

    # `run` drains once before the command and once after, so a read the
    # ceiling ends costs about that per drain, against a quiet window of 5s
    # that this server never reaches.
    ceiling_for_two_drains = 3.0 * FAST_CEILING_SECONDS
    check("a console that never goes quiet still ends the read",
          output is not None, f"still draining after {elapsed:.1f}s")
    if output is not None:
        check("a bounded read ends well inside its quiet window",
              elapsed < ceiling_for_two_drains, f"{elapsed:.1f}s")
        check("a bounded read still returns the output it collected",
              "log line of output" in output, repr(output[-80:]))
        check("a bounded read keeps no more than its cap",
              len(output) <= game_telnet.DRAIN_MAX_CHARS, str(len(output)))

    check("a zero timeout is refused before a socket is opened",
          rejects_bad_timeout(0), "connect() did not raise ValueError")
    check("a negative timeout is refused before a socket is opened",
          rejects_bad_timeout(-1.0), "connect() did not raise ValueError")
    return report()


if __name__ == "__main__":
    sys.exit(main())
