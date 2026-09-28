# C# / Harmony Mods

For behavior that can't be expressed through XML config (new game logic,
hooking into engine methods, custom UI code), mods ship a compiled C#
assembly (`.dll`) alongside `ModInfo.xml`.

## Harmony dependency

`0_TFP_Harmony` is TFP's **official** Harmony dependency — developer-provided
and pre-installed with the base game, not a third-party mod. Structurally
it's still just a modlet though (not part of `Data/Config/`, not baked into
the game binary): it follows the exact same `ModInfo.xml` + DLL layout any
other mod uses, TFP just ships it pre-installed in the base install's
`Mods/` folder (verified on disk at `Mods/0_TFP_Harmony/`) as a shared
dependency so individual mods don't each need to bundle their own copy of
Harmony:

```
0_TFP_Harmony/
├── ModInfo.xml
├── 0Harmony.dll          # Lib.Harmony — runtime IL patching library
├── TfpHarmony.dll         # Fun Pimps' own harness/loader around Harmony
├── Mono.Cecil*.dll         # IL manipulation (Harmony dependency)
├── MonoMod.*.dll            # IL manipulation (Harmony dependency)
└── System.ValueTuple.dll
```

Any mod that wants to Harmony-patch game methods references `0Harmony.dll`
at compile time and relies on `0_TFP_Harmony` being present and loading
first (hence its `0_` name prefix — see load order in `mod-structure.md`).

For local reference, inspect only `<game install>/Mods/`. Do not use sibling
or backup directories as evidence for the current local install.

## General pattern (standard Harmony usage — not verified by decompiling
these specific DLLs, but this is the standard/documented approach)

```csharp
[HarmonyPatch(typeof(SomeGameClass), "SomeMethod")]
public class SomeGameClass_SomeMethod_Patch
{
    static bool Prefix(SomeGameClass __instance, ref int someArg)
    {
        // return false to skip the original method, true to let it run
        return true;
    }

    static void Postfix(SomeGameClass __instance)
    {
        // runs after the original method
    }
}
```

A mod's DLL typically has a `ModApi`-implementing entry class that Harmony's
`PatchAll()` is invoked from on mod load.

## Mod settings file (runtime config the mod reads itself)

The hordeforge default for a mod's own tunables is a **TOML file the DLL
reads itself**: `Config/<Mod>.toml` in the installed mod folder, resolved
from the path the game hands you (`_modInstance.Path` in `InitMod`) — never
a hardcoded path or the working directory. The engine's XML patcher never
sees it (the patcher only opens `Config/` files named after vanilla files),
and net48 has no TOML library, so the template ships a fail-loud TOML
subset parser (`TomlSettings.cs`: bare keys, booleans, numbers, strings,
arrays; tables and dotted keys rejected).

The scaffolded wiring (`ModSettings.cs` + the mod's console command)
carries the full contract, taken from AtomicDoomsday (its ADRs 0006/0015):

- applied at `InitMod`; a missing file is the normal fresh-install case
  (defaults stand, one log line says so)
- **saving the file applies without a restart**: the file text is re-read
  from `ModEvents.UnityUpdate` and compared with what is applied, debounced
  so a half-written save is not applied; `<mod> reload` re-reads
  immediately. Change detection is the text, not an mtime/length stamp: a
  same-length save inside one mtime tick leaves the stamp identical, and
  the old values would then stand until the next edit
- a reload **resets to shipped defaults, then applies the file**; a broken
  save keeps the current values and logs the error
- a file the engine cannot stat or open is **logged with the underlying
  cause, once per cause** — the watch polls several times a second, so a
  swallowed read failure would leave the mod on defaults forever, silently
- the console command's `set` shares one name/value grammar with the file
  via `ModSettings.TrySet`, and changes the session only until the file is
  re-read
- `ModSettings.Applied` fires after each apply — the hook for anything
  that must react to changed values (synced CVars, a future settings UI)

In multiplayer the **server's copy is authoritative** for server-side
behavior; when clients need the values, sync them explicitly (AtomicDoomsday
pushes them through player CVars — its ADR 0012 pattern).
`scripts/test_settings_reload.py` holds the source-level contract offline.

### Who may run a console command

A `ConsoleCmdAbstract` subclass is a privileged surface: every connected
player can type it. Two members of the command decide what happens, and
neither is checked inside `Execute`.

**`DefaultPermissionLevel`** is the required level, where **0 is the most
privileged** and a larger number is less privileged (an unlisted player is
`Constants.cDefaultUserPermissionLevel`, 1000). The engine enforces it
*upstream* of `Execute`:

| Caller | Gate |
|---|---|
| connected client (`NetPackageConsoleCmdServer`) | `ConnectionManager.ServerConsoleCommand` → `AdminTools.CommandAllowedFor`: allowed when the caller's level is at or below the command's; denied callers get the engine's permission error |
| web dashboard Command API | the same `CommandAllowedFor` call, for the bound web user |
| dedicated telnet, stdin, the in-game local console | none; these are the operator's own channels |

`ServerConsoleCommand` checks the level *before* anything else runs, so a
command that is admin-level is unreachable from a player client however it
is written. The base class returns 0, so a command that overrides nothing is
admin-only by default; state the level anyway, because the base class is the
game's and a mod's permission should not depend on it. State a larger number
only for a command that is safe for any player, and say why in the help text.

**`IsExecuteOnClient`** decides *where* it runs, not who may run it. A
client-executable command is forwarded to the caller and executed in that
caller's own process, so on a dedicated server it edits the caller's copy of
anything it writes, not the server's. A command that reads or writes
server-authoritative state is `false`.

Both are held at the source level by
`scripts/test_console_command_permissions.py`; the live behavior is proven in
game. The engine's side is catalogued in
`hordeforge/7dtd-engine-research` `docs/admin/console-commands.md`.

### Comments are the settings UI

Wrench (`hordeforge/7dtd-mod-settings`) renders every installed mod's
`Config/<Mod>.toml` in the game's options menu and edits it in place, so
the file's comments are player-facing:

- The **contiguous comment block directly above a key** is that key's
  help text (a blank line detaches it; a comment trailing a value on the
  same line belongs to no key).
- The block may **end** with one structured line declaring the value's
  choices, which Wrench turns into a typed control:

  ```toml
  # ui: flags TokenA,TokenB,TokenC     -> checkboxes + an "all" master
  #    (writes true for all, false for none, else the checked array)
  # ui: enum a,b,c                     -> single choice
  # ui: range 0..1                     -> numeric bounds
  ```

  The mod's own `TrySet` stays the validator; the annotation only shapes
  the control. Without one, Wrench falls back to a raw-value text field
  (plus a flip button on booleans), so annotations are optional per key.
  Convention owner: Wrench's `docs/design.md`.

## When you actually need this vs. XML

Prefer XML (`xml-patching.md`) whenever the desired behavior is expressible
as config: new items/blocks/entities, stat tweaks, recipes, loot, buffs,
explosion parameters, etc. — this covers a large fraction of "new
weapon/item" style mods without any C# at all (see `thrownGrenadeNukeAdmin`
in vanilla `items.xml`, a full nuke-grenade item defined purely in XML).
Reach for a Harmony DLL only when the change requires new logic the XML
system has no hook for.
