__MOD_DISPLAY_NAME__ 0.1.0.0

7 DAYS TO DIE V3.2

INSTALL

Extract this folder so ModInfo.xml is located at:

  7 Days To Die/Mods/__MOD_NAME__/ModInfo.xml

For a dedicated server, install the same complete folder in the server's
Mods directory. XML-only mods push config to joining clients; a mod DLL or
custom assets must also be installed on every player client.

REQUIREMENTS

Keep the stock 0_TFP_Harmony mod installed. Do not include another Harmony
copy in this folder. If this mod ships a DLL, disable Easy Anti-Cheat on
client and server.

CONTENT

__MOD_PURPOSE__

TROUBLESHOOTING

After startup, check the game log for "Loaded Mod: __MOD_NAME__" (and the
[__MOD_NAME__] init lines if this mod ships a DLL). For XML or Harmony
errors, remove the mod, confirm the game starts, then restore the complete
folder. Client and server must use the same mod version in multiplayer.
