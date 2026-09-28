#!/usr/bin/env python3
"""A telnet session replays from its clock, not from the wall clock's timing.

`GameTelnet` is the mod's oracle: every check that asks "what does the game
think is true?" goes through it, and what it returns depends on when bytes
arrive. The retry that succeeds on the third attempt, the ready marker split
across two packets, the drain window that restarts on every chunk: each is
decided by `time.monotonic()`, so with the real clock they can only be
exercised by waiting them out, and when they do go wrong the wait is over
before anybody can look at it. The other telnet gate covers this over real
sockets, which is the honest way to test a socket, and cannot force any of
these three.

So the intervals are injected and this gate drives them: a scripted console
hands over named chunks, a virtual clock records every wait, and each run
asserts the exact attempt count, the exact wait sequence, and the exact text
that comes back. Two runs are identical by construction, which is what makes
a failure reproducible.
"""

from __future__ import annotations

import contextlib
import math
import os
import sys
from collections.abc import Iterator
from typing import NamedTuple

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import game_telnet
from gate import check
from gate import main as report


class VirtualClock:
    """A clock that only moves when the client waits.

    `sleep` records the interval and advances the reading; nothing else moves
    time, so a run costs microseconds and the wait sequence is an assertion
    rather than an observation.
    """

    def __init__(self) -> None:
        self.seconds = 0.0
        self.waits: list[float] = []

    def now(self) -> float:
        return self.seconds

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.seconds += seconds


class ScriptedSocket:
    """A descriptor a scripted console answers on, one packet per recv.

    `select` decides whether the client reads at all, so the scripted packets
    are published through a real pipe: the next one is written when the
    previous is taken, and the pipe is drained on the way out. Readiness is
    therefore the OS's answer to what the script said, not a guess, and a
    client that never waits is still never given a packet it has not earned.
    """

    def __init__(self, packets: list[bytes], send_raises: BaseException | None = None,
                 close_raises: BaseException | None = None) -> None:
        self.sent: list[bytes] = []
        self.closed = False
        self.timeouts: list[float] = []
        self._queue = list(packets)
        self._send_raises = send_raises
        self._close_raises = close_raises
        self._read_end, self._write_end = os.pipe()
        self._publish()

    def _publish(self) -> None:
        if self._queue:
            os.write(self._write_end, self._queue[0])

    def fileno(self) -> int:
        return self._read_end

    def settimeout(self, seconds: float) -> None:
        self.timeouts.append(seconds)

    def recv(self, _size: int) -> bytes:
        # The pipe is what made the client read; the text returned is the
        # script's, so a packet boundary can be placed wherever the scenario
        # needs one.
        os.read(self._read_end, 65536)
        packet = self._queue.pop(0)
        self._publish()
        return packet

    def sendall(self, data: bytes) -> None:
        if self._send_raises is not None:
            raise self._send_raises
        self.sent.append(data)

    def close(self) -> None:
        self.closed = True
        for fd in (self._read_end, self._write_end):
            with contextlib.suppress(OSError):
                os.close(fd)
        if self._close_raises is not None:
            raise self._close_raises


BANNER = b"7 Days To Die\r\n\r\nPress 'help' to get a list of all commands\r\n"
ANSWER = b"\r\ngive\r\nExecuting command give\r\n\r\nSpawn count: 3\r\n"


class Attempt(NamedTuple):
    """One dial: where it went, and how long it was willing to wait."""

    address: tuple[str, int]
    timeout: float | None



@contextlib.contextmanager
def refusing(failures: int, then: ScriptedSocket | None) -> Iterator[list[Attempt]]:
    """A listener that refuses `failures` connections before answering.

    Yields the attempt log: the address each attempt named, and the timeout it
    was offered. The second half is a property of its own, because a retry
    that quietly widens the connect timeout changes how long a failed session
    hangs without changing a line of the client's code.
    """
    attempts: list[Attempt] = []
    sock = then
    real = game_telnet.socket.create_connection

    def create_connection(address: tuple[str, int],
                          timeout: float | None = None) -> ScriptedSocket:
        attempts.append(Attempt(address, timeout))
        if len(attempts) <= failures:
            raise ConnectionRefusedError("the listener is not open yet")
        assert sock is not None
        return sock

    game_telnet.socket.create_connection = create_connection
    try:
        yield attempts
    finally:
        game_telnet.socket.create_connection = real


def client(clock: VirtualClock, sock: ScriptedSocket | None = None,
           timeout: float = 10.0) -> game_telnet.GameTelnet:
    telnet = game_telnet.GameTelnet("127.0.0.1", 8081, timeout=timeout,
                                    now=clock.now, sleep=clock.sleep)
    if sock is not None:
        telnet._sock = sock
    return telnet


def connects_after_the_listener_opens() -> None:
    """A server that takes three tries is reached on the third, not the first."""
    clock = VirtualClock()
    sock = ScriptedSocket([BANNER])
    telnet = client(clock)
    with refusing(2, sock) as attempts:
        telnet.connect(wait=60.0)

    check("the client retries a refused connection", len(attempts) == 3,
          f"made {len(attempts)} attempts, wanted 3")
    check("every attempt, retry included, offers the session timeout",
          [a.timeout for a in attempts] == [10.0] * 3, repr(attempts))
    check("every attempt dials the address the client was built with",
          [a.address for a in attempts] == [("127.0.0.1", 8081)] * 3, repr(attempts))
    retries = [w for w in clock.waits if w == game_telnet.CONNECT_RETRY_SECONDS]
    polls = [w for w in clock.waits if w == game_telnet.POLL_INTERVAL_SECONDS]
    check("a refusal waits the retry interval, never the whole budget",
          retries == [game_telnet.CONNECT_RETRY_SECONDS] * 2, repr(clock.waits))
    # The banner window is polled to the clock, so it carries the deadline over
    # by the one interval it is in: 0.05 does not accumulate to exactly 0.5, and
    # a gate that pinned the count would be pinning that rounding instead of
    # the behaviour.
    wanted = math.ceil(game_telnet.BANNER_DRAIN_SECONDS
                       / game_telnet.POLL_INTERVAL_SECONDS) + 1
    check("the banner window is polled, not spun",
          polls == [game_telnet.POLL_INTERVAL_SECONDS] * wanted, repr(clock.waits))
    check("nothing else is waited on", len(polls) + len(retries) == len(clock.waits),
          repr(clock.waits))


def a_marker_split_across_packets_is_found() -> None:
    """A ready marker the server split mid-word is still a ready marker."""
    split = BANNER.index(b"Press")
    clock = VirtualClock()
    sock = ScriptedSocket([BANNER[:split + 5], BANNER[split + 5:]])
    telnet = client(clock, sock)
    seen = telnet._read_until_any(game_telnet.READY_MARKERS, timeout=10.0)
    check("a marker split across two packets is found",
          "Press 'help' to get a list of all commands" in seen, repr(seen))
    # Both packets are in hand, so the search never fell back to polling.
    check("a complete marker costs no wait at all", clock.waits == [], repr(clock.waits))


def a_marker_split_that_never_completes_times_out() -> None:
    """The same split, left unfinished, ends in the error that names it."""
    split = BANNER.index(b"Press")
    clock = VirtualClock()
    sock = ScriptedSocket([BANNER[:split + 5]])
    telnet = client(clock, sock, timeout=0.1)
    try:
        telnet._read_until_any(game_telnet.READY_MARKERS, timeout=0.1)
        raised = ""
    except game_telnet.TelnetError as exc:
        raised = str(exc)
    check("an unfinished marker raises rather than returning",
          "timed out waiting for" in raised, repr(raised))
    check("the error names the marker it was waiting for",
          "Press 'help'" in raised, repr(raised))
    check("a 0.1s deadline is two polls, never a spin",
          clock.waits == [game_telnet.POLL_INTERVAL_SECONDS] * 2, repr(clock.waits))


def the_retry_loop_gives_up_at_its_deadline() -> None:
    """A listener that never opens costs the budget and then stops."""
    clock = VirtualClock()
    telnet = client(clock)
    with refusing(1000, None):
        try:
            telnet.connect(wait=0.0)
            raised = ""
        except game_telnet.TelnetError as exc:
            raised = str(exc)
    check("a listener that never opens fails the connect", "could not connect" in raised,
          repr(raised))
    check("the error says the wait it gave up after", "within 0s" in raised, repr(raised))
    # wait=0.0 admits no attempt at all: the deadline is checked before the
    # first try, so a zero budget never opens a socket.
    check("a zero budget makes no attempt", not clock.waits, repr(clock.waits))


def the_drain_window_waits_out_its_poll() -> None:
    """The window ends on the clock, after the scripted packets are collected."""
    clock = VirtualClock()
    sock = ScriptedSocket([ANSWER])
    telnet = client(clock, sock)
    collected = telnet._drain(0.1)
    check("every scripted packet is collected", collected == ANSWER.decode(),
          repr(collected))
    # Each poll costs POLL_INTERVAL_SECONDS, so a 0.1s window is exactly two
    # and the loop cannot overrun into a third.
    check("the window is polled, not spun",
          clock.waits == [game_telnet.POLL_INTERVAL_SECONDS] * 2, repr(clock.waits))
    check("the drain reads with a short timeout",
          game_telnet.DRAIN_READ_TIMEOUT_SECONDS in sock.timeouts,
          repr(sock.timeouts))
    check("the drain restores the session timeout", sock.timeouts[-1] == 10.0,
          repr(sock.timeouts))


def a_server_hangup_ends_the_window() -> None:
    """A read failure ends the collection instead of raising out of it."""

    class Hangup(ScriptedSocket):
        def recv(self, _size: int) -> bytes:
            os.read(self._read_end, 65536)
            self._queue.clear()
            return b""

    clock = VirtualClock()
    sock = Hangup([b"partial"])
    telnet = client(clock, sock)
    collected = telnet._drain(0.1)
    check("a hangup during a drain ends the window without raising",
          telnet.closed_by_server and collected == "",
          f"closed={telnet.closed_by_server} collected={collected!r}")


def the_farewell_waits_out_its_settle() -> None:
    """close() holds the socket open for the settle window, on the injected clock."""
    clock = VirtualClock()
    sock = ScriptedSocket([])
    telnet = client(clock, sock)
    telnet.close()
    check("the farewell is sent before the socket drops", sock.sent == [b"exit\r\n"],
          repr(sock.sent))
    check("the close waits the settle window",
          clock.waits == [game_telnet.CLOSE_SETTLE_SECONDS], repr(clock.waits))
    check("the socket is released", sock.closed and telnet._sock is None)


def main() -> int:
    connects_after_the_listener_opens()
    a_marker_split_across_packets_is_found()
    a_marker_split_that_never_completes_times_out()
    the_retry_loop_gives_up_at_its_deadline()
    the_drain_window_waits_out_its_poll()
    a_server_hangup_ends_the_window()
    the_farewell_waits_out_its_settle()
    return report()


if __name__ == "__main__":
    sys.exit(main())
