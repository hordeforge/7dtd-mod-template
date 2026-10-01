"""Talk to a dedicated server's telnet console.

This is the oracle the screenshot-driven checks should be using wherever the
question is "what does the game think is true?" rather than "what is drawn on
screen". It is faster than OCR, exact, and — the part the client cannot give
us at all — it returns each command's **output**, not just the fact that the
command ran. The client log records that a command executed but never what it
printed, which is why `giveself` looked broken when it was quietly dropping
items into the world.

Telnet is dedicated-server only. `GameManager` starts it under
`if (IsDedicatedServer && GamePrefs.GetBool(EnumGamePrefs.TelnetEnabled))`
(read with `ilspycmd`), so enabling the pref on a client does nothing at all.

With an empty `TelnetPassword` the server binds the listener to loopback
rather than all interfaces (`TelnetConsole`'s constructor:
`new TcpListener(authEnabled ? IPAddress.Any : IPAddress.Loopback, port)`),
so a passwordless local console is not exposed off the machine. Setting a
password therefore moves the listener to every interface while the transport
stays unencrypted, so a non-loopback host is warned about on stderr and the
password is redacted from the one error that carries a line this client sent
(a failed write out of `send_raw`).

Standard library only — no telnetlib, which was removed in Python 3.13.
"""

from __future__ import annotations

import codecs
import contextlib
import ipaddress
import re
import select
import socket
import sys
import time
from typing import Callable

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8081
# The server prints this once it wants the password, when one is configured.
PASSWORD_PROMPT = ("Please enter password:",)
# How long the server is given to act on the farewell before the socket drops.
CLOSE_SETTLE_SECONDS = 0.2
# The ceiling on one collection, whatever the idle window says. Generous
# against a settle of well under a second, and short enough that a console
# printing without pause costs a caller a bounded wait.
DRAIN_TOTAL_CAP_SECONDS = 30.0
# The most characters one collection keeps. A console printing without pause
# for the whole time cap would otherwise grow the result for as long as it
# talks. What arrives past the cap is read and dropped, so the next command
# still starts on a drained socket.
DRAIN_TOTAL_CAP_CHARS = 4_000_000
# The server prints this once the console is ready to take commands.
READY_MARKERS = ("Press 'help' to get a list of all commands", "Logon successful")
REDACTED = "<redacted>"

# Every interval this client waits on, named once. They are the client's whole
# observable timing, so a caller simulating a session overrides them through
# the clock rather than waiting them out.
# Between two attempts to reach a listener that has not opened yet.
CONNECT_RETRY_SECONDS = 2.0
# How long the banner is collected for once the ready marker has been seen.
BANNER_DRAIN_SECONDS = 0.5
# How long the console is given to finish the previous command before a new one.
PRE_COMMAND_DRAIN_SECONDS = 0.1
# How long a command's output is collected for when the caller names no window.
DEFAULT_SETTLE_SECONDS = 0.8
# What a wait costs when nothing has arrived yet.
POLL_INTERVAL_SECONDS = 0.05
# How long select may block before the loop looks at the clock again.
READABLE_WAIT_SECONDS = 0.2
# The read timeout _drain installs, short enough that a chunk arriving inside
# the window is collected rather than waited for.
DRAIN_READ_TIMEOUT_SECONDS = 0.3


class TelnetError(RuntimeError):
    pass


# The only two byte sequences that end a line on this wire, in either order.
# str.splitlines() is not that rule: it also breaks on NEL, LINE SEPARATOR,
# PARAGRAPH SEPARATOR, LS, PS and the vertical/horizontal separators, so one
# printed line carrying U+2028 came back as two, and a caller matching the
# output against what the server said never matched.
WIRE_LINE_BREAKS = re.compile(r"\r\n|\r|\n")


def wire_lines(text: str) -> list[str]:
    """`text` split on the protocol's line terminators only."""
    return WIRE_LINE_BREAKS.split(text)


def command_output(raw: str, command: str) -> str:
    """`raw`, as read off the wire, reduced to a command's output.

    Three kinds of line are dropped: blank ones, the server's echo of the
    command itself, and the engine's `Executing command` notice. Nothing
    re-derives them, so a caller needing the raw stream has to read it itself.
    """
    lines = [line.rstrip("\r") for line in wire_lines(raw)]
    cleaned = [
        line for line in lines
        if line.strip() and line.strip() != command
        and "Executing command" not in line
    ]
    return "\n".join(cleaned)


def is_loopback(host: str) -> bool:
    """Whether `host` names this machine, so traffic never leaves it.

    A hostname that does not resolve is reported as not loopback: the caller
    only uses this to decide whether to warn, and a failed lookup is not
    evidence that the connection stays local.
    """
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    try:
        addresses = {entry[4][0] for entry in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return bool(addresses) and all(
        ipaddress.ip_address(address).is_loopback for address in addresses)


class GameTelnet:
    """A minimal client for the 7DTD telnet console."""

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 password: str = "", timeout: float = 10.0,
                 now: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        # The clock is a parameter, not a call to time: every wait in this
        # client is a deadline, and a deadline read from the real clock can only
        # be exercised by waiting it out, so a retry that lands on the third
        # attempt and a marker split across two packets are untestable and a
        # run cannot be replayed. Defaults are the real clock, so production
        # wiring is unchanged.
        self._now = now
        self._sleep = sleep
        self._sock: socket.socket | None = None
        self.closed_by_server = False
        # TCP delivers a byte stream, not characters: a multi-byte UTF-8
        # sequence can straddle any two recv() boundaries. A per-chunk
        # decode turned every such split into U+FFFD, so one non-ASCII
        # character in a command's output arrived corrupted. This decoder
        # carries the incomplete tail of a chunk into the next one and still
        # replaces bytes that are not UTF-8 at all.
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def _describe(self, line: str) -> str:
        """The line as it may appear in an error message.

        The console password goes down the same path as every command, so it is
        the one line that must never reach a log or a traceback.
        """
        if self.password and line == self.password:
            return REDACTED
        return repr(line)

    # -- connection -------------------------------------------------------

    def __enter__(self) -> GameTelnet:
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def connect(self, wait: float = 120.0) -> None:
        """Connect, retrying until the server has opened its listener."""
        # A timeout of 0 makes the socket non-blocking: every attempt failed
        # with BlockingIOError until `wait` ran out, reported as a server that
        # is not running.
        if self.timeout <= 0:
            raise ValueError(f"timeout must be positive, not {self.timeout!r}")
        # A reconnect on a live instance would otherwise drop the previous
        # socket on the floor: nothing else releases it.
        self.close()
        # Deadlines use the monotonic clock: an NTP step mid-wait would make a
        # wall-clock deadline expire instantly or hang for the skew duration.
        deadline = self._now() + wait
        last: Exception | None = None
        # A new session starts at a character boundary: bytes carried over
        # from a previous connection would open the first line with a
        # replacement character.
        self._decoder.reset()
        # And with a server that has not hung up yet: one session that ended
        # in a read error otherwise left every later close() on this instance
        # skipping the farewell.
        self.closed_by_server = False
        while self._now() < deadline:
            try:
                self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
                self._sock.settimeout(self.timeout)
                break
            except OSError as exc:
                last = exc
                self._sleep(CONNECT_RETRY_SECONDS)
        else:
            raise TelnetError(
                f"could not connect to the telnet console at {self.host}:{self.port} "
                f"within {wait:.0f}s ({last}). Is the dedicated server running with "
                "TelnetEnabled=true in its config?"
            )

        try:
            if self.password:
                if not is_loopback(self.host):
                    # The console is telnet, so the password crosses the wire in
                    # cleartext. Setting TelnetPassword is also what makes the
                    # engine bind IPAddress.Any instead of loopback, so a
                    # passworded remote console is exactly the exposed case.
                    print(f"WARNING: sending the telnet password in cleartext to "
                          f"{self.host}:{self.port}; the console has no transport "
                          f"security. Keep it on loopback or tunnel it over SSH.",
                          file=sys.stderr)
                self._read_until_any(PASSWORD_PROMPT, timeout=self.timeout)
                self.send_raw(self.password)
            # Drain the banner so the first command's output is not mixed with it.
            self._read_until_any(READY_MARKERS, timeout=self.timeout, required=False)
            self._drain(BANNER_DRAIN_SECONDS)
        except Exception:
            # The socket is open but the session never became usable, so
            # release it here: __exit__ does not run when __enter__ raised,
            # and a caller that only closes after connect() returned has
            # nothing to close. Any exception type, not just TelnetError, or a
            # decode error on the banner leaks the descriptor for the life of
            # the process.
            self.close()
            raise

    def close(self) -> None:
        sock, self._sock = self._sock, None
        if sock is None:
            return
        try:
            if not self.closed_by_server:
                # Hang up politely so the server logs the shutdown; a connection
                # the server already dropped has nothing left to say. Best-effort
                # farewell: the server may already be gone, and a failed send
                # must not skip the close below.
                try:
                    sock.sendall(b"exit\r\n")
                    self._sleep(CLOSE_SETTLE_SECONDS)
                except OSError:
                    pass
        finally:
            with contextlib.suppress(OSError):
                sock.close()

    # -- io ---------------------------------------------------------------

    def send_raw(self, line: str) -> None:
        if self._sock is None:
            raise TelnetError("not connected")
        try:
            self._sock.sendall((line + "\r\n").encode("utf-8", "replace"))
        except OSError as exc:
            raise TelnetError(f"sending {self._describe(line)} failed: {exc}") from exc

    def _recv(self) -> str:
        if self._sock is None:
            raise TelnetError("not connected")
        try:
            data = self._sock.recv(65536)
        except socket.timeout:
            return ""
        except OSError as exc:
            raise TelnetError(f"reading from the console failed: {exc}") from exc
        if not data:
            raise TelnetError("the server closed the telnet connection")
        return self._decoder.decode(data)

    def _drain(self, seconds: float) -> str:
        """Collect whatever arrives over a short window.

        Any read failure ends the collection rather than raising, because the
        commands that legitimately end the session (`shutdown` being the
        obvious one) should still have their output returned. A transport
        failure and a server hangup therefore end the window the same way, and
        both leave the connection marked closed: nothing that follows can
        recover a session whose reads have already failed.

        The window is an *idle* window, so it is extended by every chunk that
        arrives. That extension is what makes a long answer come back whole,
        and without a ceiling it is also what never ends it: a console that
        keeps printing (a server announcing a status line, a command whose
        output runs for minutes) refreshed `end` on every read and `run()`
        never returned, hanging the oracle session on a stream that was never
        going to stop. DRAIN_TOTAL_CAP_SECONDS bounds the whole collection,
        so a busy console yields everything printed up to the cap and the
        caller gets its answer instead of no answer at all. The result keeps
        at most DRAIN_TOTAL_CAP_CHARS characters, the first ones printed.
        """
        started = self._now()
        end = started + seconds
        chunks: list[str] = []
        kept = 0
        if self._sock is not None:
            self._sock.settimeout(DRAIN_READ_TIMEOUT_SECONDS)
            while self._now() < end and self._now() - started < DRAIN_TOTAL_CAP_SECONDS:
                try:
                    chunk = self._recv() if self._readable() else ""
                except TelnetError:
                    self.closed_by_server = True
                    break
                if chunk:
                    # Collected, not concatenated: `collected += chunk` copies
                    # everything read so far on every chunk, so draining a long
                    # command's output cost a quadratic number of character
                    # copies before the first byte was returned.
                    if kept < DRAIN_TOTAL_CAP_CHARS:
                        chunks.append(chunk[:DRAIN_TOTAL_CAP_CHARS - kept])
                        kept += len(chunks[-1])
                    end = self._now() + seconds
                else:
                    self._sleep(POLL_INTERVAL_SECONDS)
            if self._sock is not None and not self.closed_by_server:
                self._sock.settimeout(self.timeout)
        return "".join(chunks)

    def _readable(self) -> bool:
        if self._sock is None:
            return False
        return bool(select.select([self._sock], [], [], READABLE_WAIT_SECONDS)[0])

    def _read_until_any(self, markers: tuple[str, ...], timeout: float,
                        required: bool = True) -> str:
        deadline = self._now() + timeout
        # Each read is searched from just before the previous one ended, which
        # is all a marker spanning a recv() boundary needs; re-searching the
        # whole buffer on every chunk is quadratic in however much the server
        # printed before the marker turned up. The chunks are held in a list
        # for the same reason: appending to one string recopies everything
        # read so far per chunk.
        overlap = max(len(marker) for marker in markers) - 1
        chunks: list[str] = []
        tail = ""
        while self._now() < deadline:
            if self._readable():
                chunk = self._recv()
                if chunk:
                    chunks.append(chunk)
                    window = tail + chunk
                    if any(marker in window for marker in markers):
                        return "".join(chunks)
                    tail = window[-overlap:] if overlap else ""
            else:
                self._sleep(POLL_INTERVAL_SECONDS)
        seen = "".join(chunks)
        if not required:
            return seen
        wanted = ", ".join(repr(marker) for marker in markers)
        raise TelnetError(f"timed out waiting for {wanted}; saw {seen[-300:]!r}")

    # -- commands ---------------------------------------------------------

    def run(self, command: str, settle: float = DEFAULT_SETTLE_SECONDS) -> str:
        """Run a console command and return its output.

        The three line kinds `command_output` drops are dropped here too.
        """
        self._drain(PRE_COMMAND_DRAIN_SECONDS)
        self.send_raw(command)
        return command_output(self._drain(settle), command)
