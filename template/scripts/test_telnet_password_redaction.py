#!/usr/bin/env python3
"""The telnet console password must not reach an error message or a traceback.

`GameTelnet` sends the password through the same `send_raw` path as every
console command, and that path used to name the line it was sending. One
failed write, or one uncaught `TelnetError` in a caller, and the dedicated
server's console password landed in the log. These assertions pin the
redaction, and pin that a non-loopback passworded console is announced.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

import game_telnet  # noqa: E402
from gate import check, main as report  # noqa: E402

PASSWORD = "hunter2-console-password"


def main() -> int:
    client = game_telnet.GameTelnet(password=PASSWORD)

    check("the password is not described back in an error",
          game_telnet.REDACTED in client._describe(PASSWORD)
          and PASSWORD not in client._describe(PASSWORD))

    check("an ordinary command is still described in full",
          "giveself" in client._describe("giveself"))

    # A passwordless client has nothing to redact, so nothing is swallowed.
    check("a passwordless client reports its commands verbatim",
          game_telnet.GameTelnet()._describe("giveself") == "'giveself'")

    # A write failure is the path that used to leak: drive it for real.
    error = _send_failure(client, PASSWORD)
    check("a failed password write does not leak the password",
          PASSWORD not in str(error), str(error))

    for host, expected in (("127.0.0.1", True), ("::1", True), ("localhost", True),
                           ("10.0.0.5", False), ("0.0.0.0", False),
                           ("host.invalid.", False)):
        check(f"{host!r} loopback classification",
              game_telnet.is_loopback(host) is expected)

    return report()


def _send_failure(client: game_telnet.GameTelnet, line: str) -> Exception:
    """The TelnetError `send_raw` raises for a line it cannot write."""
    class Dead:
        def sendall(self, _data: bytes) -> None:
            raise OSError("broken pipe")

    client._sock = Dead()  # type: ignore[assignment]
    try:
        client.send_raw(line)
    except game_telnet.TelnetError as error:
        return error
    finally:
        client._sock = None
    raise AssertionError("send_raw on a dead socket did not raise")


if __name__ == "__main__":
    raise SystemExit(main())
