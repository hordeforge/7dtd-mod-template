#!/usr/bin/env python3
"""The offline runner itself must not be able to report a false green run.

`run-offline-tests.sh` decides PASS/FAIL for every other scripts/test_*.py,
so a regression in its exit-code plumbing would silence the entire suite at
once — the exact failure nothing else here can catch. Its docstring pins four
guarantees; this gate drives each one against fixture copies of the runner in
a throwaway directory, never against the shared tree:

1. every fixture test passing, no filter -> exit 0;
2. one fixture test failing -> nonzero, and the FAIL line names it;
3. a filter matching no test name -> exit 1 (must not read as a green run);
4. a filter naming a subset -> only that subset runs;
5. two runs over the same tree print byte-identical stdout.

(5) is the gate the runner owes AGENTS.md's "every gate is deterministic" rule:
a report carrying an elapsed time or a finish-order-dependent line makes two
runs of an unchanged tree differ, so a diff of one run against another proves
nothing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
from gate import check, main as report  # noqa: E402

PASS_BODY = "#!/usr/bin/env python3\nprint('ok')\n"
FAIL_BODY = "#!/usr/bin/env python3\nimport sys\nprint('boom')\nsys.exit(3)\n"
TIMING = re.compile(r"\(\d+s\)")


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

        clean = run_runner(good)
        check(
            "all fixtures passing, no filter, exits 0",
            clean.returncode == 0 and "2 offline tests run" in clean.stdout,
            f"exit={clean.returncode} stdout={clean.stdout!r}",
        )

        again = run_runner(good)
        check(
            "two runs over the same tree print byte-identical stdout",
            again.stdout == clean.stdout and again.returncode == clean.returncode,
            f"first={clean.stdout!r} second={again.stdout!r}",
        )

        timed = run_runner(good, env={**os.environ, "OFFLINE_TEST_TIMINGS": "1"})
        check(
            "elapsed seconds appear only under OFFLINE_TEST_TIMINGS=1",
            timed.returncode == 0
            and TIMING.search(timed.stdout) is not None
            and TIMING.search(clean.stdout) is None,
            f"default={clean.stdout!r} timed={timed.stdout!r}",
        )

        filtered = run_runner(good, "alpha")
        check(
            "a filter runs only the tests its substrings match",
            filtered.returncode == 0 and "1 offline tests run" in filtered.stdout,
            f"exit={filtered.returncode} stdout={filtered.stdout!r}",
        )

        nomatch = run_runner(good, "zzz-no-such-test")
        check(
            "a filter matching nothing fails instead of reading green",
            nomatch.returncode != 0 and "no test_*.py matches" in nomatch.stderr,
            f"exit={nomatch.returncode} stderr={nomatch.stderr!r}",
        )

        make_runner_dir(root, {"test_gamma_fail.py": FAIL_BODY})
        broken = run_runner(good)
        named = [line for line in broken.stdout.splitlines() if line.startswith("FAIL ")]
        check(
            "a failing fixture test fails the whole run and is named",
            broken.returncode != 0
            and any(line.startswith("FAIL test_gamma_fail.py") for line in named),
            f"exit={broken.returncode} stdout={broken.stdout!r}",
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)

    return report()


if __name__ == "__main__":
    sys.exit(main())
