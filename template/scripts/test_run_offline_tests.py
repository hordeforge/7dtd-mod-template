#!/usr/bin/env python3
"""The offline runner itself must not be able to report a false green run.

`run-offline-tests.sh` decides PASS/FAIL for every other scripts/test_*.py,
so a regression in its exit-code plumbing would silence the entire suite at
once — the exact failure nothing else here can catch. This gate drives the
guarantees its docstring lists against fixture copies of the runner in a
throwaway directory, never against the shared tree:

1. every fixture test passing, no filter -> exit 0;
2. one fixture test failing -> nonzero, and the FAIL line names it;
3. a filter matching no test name -> exit 1 (must not read as a green run);
4. a filter naming a subset -> only that subset runs;
5. two runs over the same tree print byte-identical stdout;
6. the elapsed seconds it reports do not come from the wall clock;
7. a worker that dies, with or without a status file, is a failure, and the
   workers beside it are still reported.

(5) is the gate the runner owes AGENTS.md's "every gate is deterministic" rule:
a report carrying an elapsed time or a finish-order-dependent line makes two
runs of an unchanged tree differ, so a diff of one run against another proves
nothing.

(6) pins the clock the durations are measured on. `date +%s` follows the wall
clock, so an NTP step or a manual clock change mid-run reports a negative or
inflated duration; the runner reads /proc/uptime instead, where the kernel
provides one. The check is skipped where that file is absent, and the
`date` shim is what makes the assertion a real one: a runner that reached for
the wall clock fails loudly instead of quietly reporting the same number.

(7) covers a worker that dies before or after writing its status file. The
unset `status` the report would otherwise read is the shape that drops a
result, so both deaths have to surface as failures with the passing workers
beside them still named.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check
from gate import main as report

PASS_BODY = "#!/usr/bin/env python3\nprint('ok')\n"
FAIL_BODY = "#!/usr/bin/env python3\nimport sys\nprint('boom')\nsys.exit(3)\n"
# A worker killed by a signal reports its exit status like any other failure.
KILL_BODY = (
    "#!/usr/bin/env python3\n"
    "import os, signal\n"
    "os.kill(os.getpid(), signal.SIGKILL)\n"
)
# A worker that takes its own reporting shell down with it never writes a
# status file. The runner has to report that as a failure: the unset
# `status` it would otherwise read is the shape that loses every result the
# other workers did produce.
KILL_SHELL_BODY = (
    "#!/usr/bin/env python3\n"
    "import os, signal\n"
    "os.kill(os.getppid(), signal.SIGKILL)\n"
    "os.kill(os.getpid(), signal.SIGKILL)\n"
)
TIMING = re.compile(r"\(\d+s\)")

# Each case is a separate runner process, and the cases below only read the
# fixture tree, so they run together instead of one after another.
MAX_RUNNER_JOBS = 5

# The default-mode cases must not inherit OFFLINE_TEST_TIMINGS: this gate runs
# inside `make test`, so with the knob set the whole suite reported elapsed
# seconds and the "only under OFFLINE_TEST_TIMINGS=1" check read its own
# inherited environment and failed.
DEFAULT_ENV = {k: v for k, v in os.environ.items() if k != "OFFLINE_TEST_TIMINGS"}


def make_runner_dir(root: str, bodies: dict[str, str]) -> str:
    """Copy the real runner plus fixture test_*.py into <root>/scripts."""
    scripts = os.path.join(root, "scripts")
    os.makedirs(scripts, exist_ok=True)
    shutil.copy(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "run-offline-tests.sh"),
        os.path.join(scripts, "run-offline-tests.sh"),
    )
    for name, body in sorted(bodies.items()):
        path = os.path.join(scripts, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
    return scripts


def run_runner(scripts: str, *filters: str,
               env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["./run-offline-tests.sh", *filters],
        cwd=scripts,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
    )


def main() -> int:
    root = tempfile.mkdtemp(prefix="test-run-offline-tests-")
    try:
        good = make_runner_dir(
            root, {"test_alpha_ok.py": PASS_BODY, "test_beta_ok.py": PASS_BODY}
        )

        # The five runs below only read the fixture tree, and each is a whole
        # runner process: serialising them made this the slowest gate in the
        # suite for no reason. The sixth run needs the failing fixture to exist
        # first, so it stays after them.
        cases = [
            ("clean", (good,), DEFAULT_ENV),
            ("again", (good,), DEFAULT_ENV),
            ("timed", (good,), {**DEFAULT_ENV, "OFFLINE_TEST_TIMINGS": "1"}),
            ("filtered", (good, "alpha"), DEFAULT_ENV),
            ("nomatch", (good, "zzz-no-such-test"), DEFAULT_ENV),
        ]
        with ThreadPoolExecutor(max_workers=MAX_RUNNER_JOBS) as pool:
            runs = dict(pool.map(
                lambda case: (case[0], run_runner(*case[1], env=case[2])),
                cases,
            ))
        clean, again = runs["clean"], runs["again"]

        check(
            "all fixtures passing, no filter, exits 0",
            clean.returncode == 0 and "2 offline tests run" in clean.stdout,
            f"exit={clean.returncode} stdout={clean.stdout!r}",
        )

        check(
            "two runs over the same tree print byte-identical stdout",
            again.stdout == clean.stdout and again.returncode == clean.returncode,
            f"first={clean.stdout!r} second={again.stdout!r}",
        )

        timed = runs["timed"]
        check(
            "elapsed seconds appear only under OFFLINE_TEST_TIMINGS=1",
            timed.returncode == 0
            and TIMING.search(timed.stdout) is not None
            and TIMING.search(clean.stdout) is None,
            f"default={clean.stdout!r} timed={timed.stdout!r}",
        )

        if os.path.exists("/proc/uptime"):
            shim = os.path.join(root, "shim")
            os.makedirs(shim, exist_ok=True)
            broken_date = os.path.join(shim, "date")
            with open(broken_date, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\necho 'date must not measure' >&2\nexit 1\n")
            os.chmod(broken_date, os.stat(broken_date).st_mode | stat.S_IEXEC)
            shimmed_env = {
                **DEFAULT_ENV,
                "OFFLINE_TEST_TIMINGS": "1",
                "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}",
            }
            monotonic = run_runner(good, env=shimmed_env)
            check(
                "elapsed seconds come from a monotonic clock, not `date`",
                monotonic.returncode == 0
                and TIMING.search(monotonic.stdout) is not None
                and "date must not measure" not in monotonic.stderr,
                f"exit={monotonic.returncode} stdout={monotonic.stdout!r} "
                f"stderr={monotonic.stderr!r}",
            )

        filtered = runs["filtered"]
        check(
            "a filter runs only the tests its substrings match",
            filtered.returncode == 0 and "1 offline tests run" in filtered.stdout,
            f"exit={filtered.returncode} stdout={filtered.stdout!r}",
        )

        nomatch = runs["nomatch"]
        check(
            "a filter matching nothing fails instead of reading green",
            nomatch.returncode != 0 and "no test_*.py matches" in nomatch.stderr,
            f"exit={nomatch.returncode} stderr={nomatch.stderr!r}",
        )

        make_runner_dir(root, {"test_gamma_fail.py": FAIL_BODY})
        broken = run_runner(good, env=DEFAULT_ENV)
        named = [line for line in broken.stdout.splitlines() if line.startswith("FAIL ")]
        check(
            "a failing fixture test fails the whole run and is named",
            broken.returncode != 0
            and any(line.startswith("FAIL test_gamma_fail.py") for line in named),
            f"exit={broken.returncode} stdout={broken.stdout!r}",
        )

        # The parallel report reads a status file per worker. Both ways a
        # worker can die have to reach the report, and the passing workers
        # beside them must still be reported.
        make_runner_dir(root, {"test_delta_killed.py": KILL_BODY,
                               "test_epsilon_noreport.py": KILL_SHELL_BODY})
        killed = run_runner(good, env={**os.environ, "OFFLINE_TEST_JOBS": "2"})
        killed_named = [line for line in killed.stdout.splitlines()
                        if line.startswith("FAIL ")]
        check(
            "a worker killed by a signal fails the run and is named",
            killed.returncode != 0
            and any(line.startswith("FAIL test_delta_killed.py") for line in killed_named),
            f"exit={killed.returncode} stdout={killed.stdout!r}",
        )
        check(
            "a worker that wrote no status file is reported, not dropped",
            any("no status file" in line and "test_epsilon_noreport.py" in line
                for line in killed_named),
            f"stdout={killed.stdout!r}",
        )
        check(
            "the workers beside a killed one are still reported",
            any(line.startswith("PASS test_beta_ok.py") for line in killed.stdout.splitlines()),
            f"stdout={killed.stdout!r}",
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    return report()


if __name__ == "__main__":
    sys.exit(main())
