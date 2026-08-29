using HarmonyLib;
using System.Reflection;

namespace __MOD_NAME__
{
    public class ModApi : IModApi
    {
        public const string LogPrefix = "[__MOD_NAME__]";

        public void InitMod(Mod _modInstance)
        {
            // Fast and defensive: log, never throw if recoverable. One
            // failing Harmony target must not kill the whole mod — prefer
            // per-patch try/catch when patches become optional.
            Log.Out($"{LogPrefix} InitMod");
            ModSettings.Load(_modInstance);
            // Re-reads Config/__MOD_NAME__.toml when it is saved, via the
            // engine's UnityUpdate event (client and dedicated) — no restart,
            // no Harmony patch.
            ModEvents.UnityUpdate.RegisterHandler(OnUnityUpdate);
            new Harmony("com.__MOD_AUTHOR_LOWER__.__MOD_NAME_LOWER__")
                .PatchAll(Assembly.GetExecutingAssembly());
        }

        static void OnUnityUpdate(ref ModEvents.SUnityUpdateData data)
        {
            ModSettings.Poll();
        }
    }
}
