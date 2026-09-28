#!/usr/bin/env python3
"""The telnet client must release its socket on every close path.

`scripts/lib/game_telnet.py` is a long-lived console client: every caller holds
its descriptor for the length of an oracle session, and a close path that
skips the release leaks a file descriptor per session, not per process. The
paths worth pinning here are the ones a reader cannot see from the call site:

- the farewell `exit` send fails (the server already went away) — the socket
  must still be closed and the failure must not escape `close()`;
- `send_raw` wraps a failed send in `TelnetError`, not `OSError`, so a
  close path catching only `OSError` never reaches its own `close()`;
- `close()` is idempotent, so a caller that closes on both the error and the
  success path does not raise on the second call.

No socket is opened: the descriptor is a stub, so the gate is deterministic
and needs no server.
"""

from __future__ import annotations

import contextlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import game_telnet
from gate import check
from gate import main as report


class StubSocket:
    """Records what a caller did to the descriptor; never opens a real one."""

    def __init__(self, send_raises: BaseException | None = None,
                 close_raises: BaseException | None = None) -> None:
        self.sent: list[bytes] = []
        self.closed = False
        self._send_raises = send_raises
        self._close_raises = close_raises

    def sendall(self, data: bytes) -> None:
        if self._send_raises is not None:
            raise self._send_raises
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True
        if self._close_raises is not None:
            raise self._close_raises


def connected(sock: StubSocket) -> game_telnet.GameTelnet:
    client = game_telnet.GameTelnet()
    client._sock = sock  # the descriptor connect() would have handed back
    return client


def closes_when_the_farewell_fails() -> None:
    # OSError: what send_raw raises for a transport failure, before its wrap.
    sock = StubSocket(send_raises=OSError("broken pipe"))
    client = connected(sock)
    try:
        client.close()
        raised = ""
    except Exception as exc:  # a close that leaks also throws; both are defects
        raised = repr(exc)
    check("a failed farewell still closes the socket", sock.closed, raised)
    check("a failed farewell is swallowed by close()", not raised, raised)
    check("the socket handle is released", client._sock is None)


def close_swallows_the_wrapped_send_error() -> None:
    # What send_raw actually raises: the TelnetError wrap, not OSError. A
    # close path that catches only OSError skips its own close() entirely.
    sock = StubSocket(send_raises=game_telnet.TelnetError("send failed"))
    client = connected(sock)
    try:
        client.close()
        raised = ""
    except Exception as exc:
        raised = repr(exc)
    check("a TelnetError from the farewell still closes the socket",
          sock.closed, raised)


def close_is_idempotent() -> None:
    sock = StubSocket()
    client = connected(sock)
    client.close()
    client.close()
    check("close() twice is safe and sends exit once",
          sock.closed and sock.sent == [b"exit\r\n"], repr(sock.sent))


def close_never_raises_from_the_close_itself() -> None:
    sock = StubSocket(close_raises=OSError("already closed"))
    client = connected(sock)
    try:
        client.close()
        raised = ""
    except Exception as exc:
        raised = repr(exc)
    check("a close that itself fails does not escape",
          not raised and client._sock is None, raised)


def negative_control() -> None:
    """The old shape (no finally) really does leak, so the gates above bite."""

    def legacy_close(sock: StubSocket) -> None:
        with contextlib.suppress(OSError):
            sock.sendall(b"exit\r\n")
        with contextlib.suppress(OSError):
            sock.close()

    sock = StubSocket(send_raises=game_telnet.TelnetError("send failed"))
    # The point of the control: the old shape escapes, skipping its close.
    with contextlib.suppress(game_telnet.TelnetError):
        legacy_close(sock)
    check("negative control: the unfixed close leaks the descriptor",
          not sock.closed)


def main() -> int:
    closes_when_the_farewell_fails()
    close_swallows_the_wrapped_send_error()
    close_is_idempotent()
    close_never_raises_from_the_close_itself()
    negative_control()
    return report()


if __name__ == "__main__":
    sys.exit(main())
