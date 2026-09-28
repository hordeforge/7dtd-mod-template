using HarmonyLib;
using System.Reflection;

namespace __MOD_NAME__
{
    public class ModApi : IModApi
    {
        public const string LogPrefix = "[__MOD_NAME__]";

        public void InitMod(Mod _modInstance)
        {
            // InitMod is unguarded: whether one failing Harmony target takes
            // the whole mod down is decided by Harmony's own handling, not
            // here. A patch that must not be able to do that has to guard
            // its own body.
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
