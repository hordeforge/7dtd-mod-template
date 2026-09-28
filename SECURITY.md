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

**Handled.**

- The mod name is restricted to `^[A-Za-z][A-Za-z0-9_]*` before it reaches
  any generated script or `Makefile` (`new-mod.sh:143`). `display_name`,
  `author` and `purpose` are not format-checked; they only reach docs and
  `README.txt`.
- The config file is not sourced blind: every key it defines is checked
  against the scaffolder's known-key list, and `csharp`, `assets` and `clone`
  must be `yes` or `no`, before the file is executed (`new-mod.sh:71-93`).
  This catches a typo. It does not make the file data; the `source` at
  `new-mod.sh:83` still runs whatever the file contains.
- `.local.env` is gitignored, written `chmod 600`, and the scaffolder's
  `git add -A` runs after it exists, so machine-local paths stay out of a
  generated repository's history and out of reach of other accounts on the
  machine (`new-mod.sh:371-385`, `:395`, `template/.gitignore:5`).
- The mod's console command states its own admin permission level (0) and is
  not client-executable, so the engine's `AdminTools.CommandAllowedFor`
  refuses a connected player before the command runs, and an admin's run
  edits the server's settings rather than their own
  (`template/src/__MOD_NAME__/ConsoleCmd__MOD_NAME__.cs:25`, `:34`). A gate
  holds both properties for every console command the mod declares
  (`template/scripts/test_console_command_permissions.py`).
- Pull-request CI uses the `pull_request` trigger, so no repository secrets
  are exposed to a fork, and the job holds only `contents: read` with
  `persist-credentials: false` (`.github/workflows/ci.yml:5`, `:18-19`,
  `:32-36`).
- The telnet console client refuses to be quiet about a cleartext password
  and redacts it from anything it prints
  (`template/scripts/lib/game_telnet.py:138-149`, `:93-97`).

**Not handled.**

- The config file passed to `new-mod.sh` and the machine-local
  `.local.env` are both executed as shell code, so both are executable
  input. A conf from someone else is a conf that runs on your machine
  (`new-mod.sh:83`, `template/scripts/server-common.sh:43-50`).
- A player's own in-game console runs any console command in their own
  client process; the engine's level check covers the networked and web
  paths, and telnet, stdin and the local console are operator channels by
  design (`template/src/__MOD_NAME__/ConsoleCmd__MOD_NAME__.cs:65`).
- The dedicated-server lane requires `EACEnabled=false`, so the server
  process in that lane runs with its anti-cheat off by design
  (`template/scripts/server-smoke.sh:38`,
  `template/scripts/install-server.sh:37`).
- NuGet auditing is disabled and no dependency lockfile is committed
  (`template/src/__MOD_NAME__/__MOD_NAME__.csproj:17`).
- `actions/checkout` is pinned to a release tag, not a commit
  (`.github/workflows/ci.yml:32`), and the sibling tool checkouts the build
  invokes are not pinned at all.

Do not run this toolchain on a machine whose `.local.env` or config file came
from someone else, and do not treat the generated mod DLL as anything other than
arbitrary code running inside the game process: that is exactly what it is.
