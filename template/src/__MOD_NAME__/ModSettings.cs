using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace __MOD_NAME__
{
	/// <summary>
	/// This mod's own runtime settings, read from
	/// <c>Config/__MOD_NAME__.toml</c> in the installed mod folder.
	///
	/// The engine's XML patcher never sees the file; the DLL reads it at
	/// <c>InitMod</c> and again whenever it is saved (the file text is
	/// re-read from <c>ModEvents.UnityUpdate</c> and compared with what is
	/// applied, debounced so a half-written save is not applied). A reload
	/// resets to shipped defaults, then applies the file; a broken save keeps
	/// the current values. The console command
	/// (<c>__MOD_NAME_LOWER__ settings|set|reload</c>) shares the same value
	/// grammar through <see cref="TrySet"/>.
	///
	/// To add a setting: a Name constant, a default, a property, a line each
	/// in <see cref="ResetToDefaults"/>, <see cref="TrySet"/> and
	/// <see cref="Describe"/>, and a commented entry in the shipped TOML.
	/// </summary>
	internal static class ModSettings
	{
		public const string RelativePath = "Config/__MOD_NAME__.toml";

		public const string ExampleEnabledName = "ExampleEnabled";
		public const bool ExampleEnabledDefault = false;

		/// <summary>Example setting; replace with this mod's real options.</summary>
		public static bool ExampleEnabled { get; private set; } = ExampleEnabledDefault;

		/// <summary>Raised after a file read applied values (startup or reload).</summary>
		public static event Action Applied;

		public const float FilePollIntervalSeconds = 0.25f;
		public const float FileReloadDebounceSeconds = 0.35f;

		static string watchedPath;
		// What the applied values came from; the only "unchanged" test.
		static string appliedText;
		// The last read failure already logged, so a file the engine cannot
		// open does not print the same line on every poll.
		static string lastReadFailure;
		// The last file text that was not applied, and the time it was first
		// seen: the debounce clock, plus a rejected text that must not be
		// parsed (and logged) again until it changes.
		static string pendingText;
		static string rejectedText;
		static float seenAt = -1f;
		static float nextPollAt;

		/// <summary>
		/// Reads the settings file if it is there. A missing file is the normal
		/// case for a fresh install, not an error: the shipped defaults stand
		/// and one line says so, because a silent no-op here would look exactly
		/// like a file that was read and had no effect. After this, a save to
		/// the same file is picked up without a restart (<see cref="Poll"/> /
		/// <c>__MOD_NAME_LOWER__ reload</c>).
		/// </summary>
		public static void Load(Mod mod)
		{
			if (mod == null || string.IsNullOrEmpty(mod.Path))
			{
				Debug.LogWarning("[__MOD_NAME__] no mod path available; using default settings.");
				LogCurrent("defaults");
				return;
			}

			watchedPath = Path.Combine(mod.Path, RelativePath);
			ReloadFromWatchedFile(true, true, out _);
		}

		/// <summary>
		/// Called from <c>ModEvents.UnityUpdate</c> so a save to the TOML file
		/// applies without restarting. Returns true when values were applied.
		/// </summary>
		public static bool Poll()
		{
			if (string.IsNullOrEmpty(watchedPath))
				return false;
			var now = Time.unscaledTime;
			if (now < nextPollAt)
				return false;
			nextPollAt = now + FilePollIntervalSeconds;
			return ReloadFromWatchedFile(false, false, out _);
		}

		/// <summary>Re-read the watched TOML immediately, ignoring the debounce.</summary>
		public static bool ReloadNow(out string message)
		{
			return ReloadFromWatchedFile(true, false, out message);
		}

		static bool ReloadFromWatchedFile(bool force, bool startup, out string message)
		{
			message = null;
			if (string.IsNullOrEmpty(watchedPath))
			{
				message = "no mod path available; using default settings.";
				return false;
			}

			if (!SdFile.Exists(watchedPath))
			{
				if (appliedText == null && !startup)
				{
					message = "defaults (no " + RelativePath + ")";
					return false;
				}
				ResetToDefaults();
				appliedText = null;
				pendingText = null;
				rejectedText = null;
				LogCurrent("defaults (no " + RelativePath + ")");
				message = RelativePath + " is missing; using defaults.";
				Applied?.Invoke();
				return true;
			}

			string text;
			string failure;
			if (!TryReadText(watchedPath, out text, out failure))
			{
				ReportReadFailure("cannot read " + RelativePath + ": " + failure);
				if (startup)
				{
					LogCurrent("defaults (unreadable " + RelativePath + ")");
					message = RelativePath + " could not be read; using defaults.";
					return false;
				}
				message = RelativePath + " could not be read; keeping current settings.";
				return false;
			}

			// The text itself decides whether anything changed. A mtime+length
			// stamp cannot: a same-length save landing inside one mtime tick
			// leaves the stamp identical, and the stale values would then stand
			// until the next edit. The file is a few hundred bytes, read once
			// per poll interval.
			if (!force && text == appliedText)
			{
				pendingText = null;
				return false;
			}

			// A text that already failed to parse stays rejected: re-reading and
			// re-logging it every poll would fill the log with one error every
			// FilePollIntervalSeconds for as long as the broken file sits there.
			if (!force && text == rejectedText)
				return false;

			if (!force)
			{
				if (text != pendingText)
				{
					pendingText = text;
					seenAt = Time.unscaledTime;
					return false;
				}
				if (Time.unscaledTime - seenAt < FileReloadDebounceSeconds)
					return false;
			}

			List<TomlSettings.Entry> entries;
			string error;
			if (!TomlSettings.TryRead(text, out entries, out error))
			{
				rejectedText = text;
				pendingText = null;
				if (startup)
				{
					Debug.LogError("[__MOD_NAME__] " + RelativePath + ": " + error + "; using default settings.");
					LogCurrent("defaults");
					message = error;
					return false;
				}
				Debug.LogError("[__MOD_NAME__] " + RelativePath + ": " + error + "; keeping current settings.");
				message = error;
				return false;
			}

			ResetToDefaults();
			lastReadFailure = null;
			for (var i = 0; i < entries.Count; i++)
			{
				if (!TrySet(entries[i].Name, entries[i].Value, out var setMessage))
					Debug.LogWarning("[__MOD_NAME__] " + RelativePath + ": " + setMessage);
			}
			appliedText = text;
			pendingText = null;
			rejectedText = null;
			var source = startup ? RelativePath : "reload " + RelativePath;
			LogCurrent(source);
			message = source;
			Applied?.Invoke();
			return true;
		}

		static void ResetToDefaults()
		{
			ExampleEnabled = ExampleEnabledDefault;
		}

		/// <summary>
		/// Log why the settings file could not be read, once per distinct cause.
		/// <see cref="Poll"/> retries every <see cref="FilePollIntervalSeconds"/>,
		/// so a file the engine cannot open (deleted mid-read, a permission
		/// change) would print the same line several times a second and still
		/// never name the cause.
		/// </summary>
		static void ReportReadFailure(string reason)
		{
			if (reason == lastReadFailure)
				return;
			lastReadFailure = reason;
			Debug.LogError("[__MOD_NAME__] " + reason);
		}

		static bool TryReadText(string path, out string text, out string failure)
		{
			text = null;
			failure = null;
			try
			{
				using (var stream = SdFile.Open(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
				using (var reader = new StreamReader(stream))
					text = reader.ReadToEnd();
				return true;
			}
			catch (Exception ex)
			{
				failure = ex.Message;
				return false;
			}
		}

		/// <summary>
		/// Applies one setting by name. Shared by the file reader and the
		/// console command so both surfaces keep one name and value grammar.
		/// Unknown names and bad values fail loud and change nothing.
		/// </summary>
		public static bool TrySet(string name, string value, out string message)
		{
			if (string.Equals(name, ExampleEnabledName, StringComparison.OrdinalIgnoreCase))
			{
				bool parsed;
				if (!TryParseBool(value, out parsed))
				{
					message = ExampleEnabledName + " must be true or false, not '" + value + "'.";
					return false;
				}
				ExampleEnabled = parsed;
				message = ExampleEnabledName + " = " + (parsed ? "true" : "false");
				return true;
			}

			message = "unknown setting '" + name + "'.";
			return false;
		}

		static bool TryParseBool(string value, out bool parsed)
		{
			parsed = false;
			if (string.Equals(value, "true", StringComparison.OrdinalIgnoreCase))
			{
				parsed = true;
				return true;
			}
			return string.Equals(value, "false", StringComparison.OrdinalIgnoreCase);
		}

		/// <summary>One line per setting, for the console command.</summary>
		public static string[] Describe()
		{
			return new[]
			{
				ExampleEnabledName + " = " + (ExampleEnabled ? "true" : "false"),
			};
		}

		static void LogCurrent(string source)
		{
			Debug.Log("[__MOD_NAME__] settings (" + source + "): "
				+ string.Join(", ", Describe()));
		}
	}
}
