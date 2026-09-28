# Security

This repository is a developer toolchain: a scaffolder, shell and Python build
scripts, and a template for 7 Days To Die mods. It runs no service, listens on no
port, and handles no user data. Its full threat model, with the risk ranking and
the file references behind every entry, is in [THREAT_MODEL.md](THREAT_MODEL.md).
Read that for anything beyond this page.

## Reporting a vulnerability

No disclosure contact is configured for this repository, and no triage path
exists. Until one is set, a report has no defined destination. If you found
something, open an issue on the repository describing the boundary, the file, and
the impact, and expect no response SLA.

## Supported versions

Only the latest tag is supported, and `main` is where fixes land through the
normal branch-and-PR flow. Nothing is backported: a mod scaffolded from an
older tag stays on that tag's behavior until its author takes the change
from [`CHANGELOG.md`](CHANGELOG.md). Generated mods version themselves in
their own `ModInfo.xml` and are not covered by this repository's tags at
all.

## What is and is not protected

Stated so nobody builds on an assumption that the code does not support.

**Handled.** The mod name is restricted to `^[A-Za-z][A-Za-z0-9_]*` before it
reaches any generated script or `Makefile` (`new-mod.sh:48`). The scaffolder's
`git add -A` runs after `.local.env` is written, and that file is gitignored, so
machine-local paths stay out of a generated repository's history
(`new-mod.sh:184`, `template/.gitignore:5`). Pull-request CI uses the
`pull_request` trigger, so no repository secrets are exposed to a fork
(`.github/workflows/ci.yml:5`).

**Not handled.** The config file passed to `new-mod.sh` and the machine-local
`.local.env` are both `source`d as shell code, so both are executable input
(`new-mod.sh:31`, `template/scripts/build.sh:20`,
`template/scripts/server-common.sh:11`). The mod's console command carries no
permission check, so any connected client can change live settings
(`template/src/__MOD_NAME__/ConsoleCmd__MOD_NAME__.cs:40`). The dedicated-server
lane requires `EACEnabled=false`, so the server process in that lane runs with
its anti-cheat off by design (`template/scripts/server-smoke.sh:30`). NuGet
auditing is disabled and no dependency lockfile is committed
(`template/src/__MOD_NAME__/__MOD_NAME__.csproj:10`).

Do not run this toolchain on a machine whose `.local.env` or config file came
from someone else, and do not treat the generated mod DLL as anything other than
arbitrary code running inside the game process: that is exactly what it is.
