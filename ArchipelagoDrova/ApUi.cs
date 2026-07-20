using Drova_Modding_API.Access;
using Il2CppCommandTerminal;
using Il2CppInterop.Runtime.InteropTypes.Arrays;
using MelonLoader;
using UnityEngine;

namespace ArchipelagoDrova
{
    /// <summary>
    /// IMGUI panel and _toasts. The Drova API has no text input and no notification API, so both are
    /// rolled here. Everything is drawn with Rect-based GUI calls: GUI.Window and GUILayout.PasswordField
    /// are not present in this game's stripped IL2CPP UnityEngine.IMGUIModule.
    /// </summary>
    public class ApUi
    {
        private const KeyCode ToggleKey = KeyCode.F7;
        private const int MaxToasts = 4;
        private const float ToastLifetime = 8f;
        private const string ConnectCommandPrefix = "/connect";

        private struct Toast
        {
            public string Text;
            public float ExpiresAt;
        }

        private readonly ArchipelagoClient _client;
        private readonly ApConfig _config;
        private readonly List<Toast> _toasts = new();
        private readonly ApProgressPanel _progress;

        private bool _visible;
        private bool _progressVisible;
        private bool _cheatRegistered;
        private bool _cheatWarned;
        private string _hostField;
        private string _portField;
        private string _slotField;
        private string _passwordField;

        public ApUi(ArchipelagoClient client, ApConfig config)
        {
            _client = client;
            _config = config;
            _progress = new ApProgressPanel(client);
            _hostField = config.Host;
            _portField = config.Port.ToString();
            _slotField = config.SlotName;
            _passwordField = config.Password;
        }

        public void AddToast(string text)
        {
            if (string.IsNullOrEmpty(text))
            {
                return;
            }

            var toast = new Toast();
            toast.Text = text;
            toast.ExpiresAt = Time.realtimeSinceStartup + ToastLifetime;
            _toasts.Add(toast);
            while (_toasts.Count > MaxToasts)
            {
                _toasts.RemoveAt(0);
            }
        }

        /// <summary>
        /// Raw key poll, matching the API's own F6 inspector. An own InputActionMap would also work
        /// but the gameplay map is disabled in menus, where the connect panel is most useful.
        /// </summary>
        public void Update()
        {
            if (Input.GetKeyDown(ToggleKey))
            {
                _visible = !_visible;
            }

            float now = Time.realtimeSinceStartup;
            for (int i = _toasts.Count - 1; i >= 0; i--)
            {
                if (now >= _toasts[i].ExpiresAt)
                {
                    _toasts.RemoveAt(i);
                }
            }
        }

        public void Draw()
        {
            DrawToasts();
            if (_visible)
            {
                DrawPanel();
            }
            if (_progressVisible)
            {
                _progress.Draw();
            }
        }

        private void DrawToasts()
        {
            if (_toasts.Count == 0)
            {
                return;
            }

            float width = 440f;
            float x = Screen.width - width - 20f;
            float y = 20f;
            for (int i = 0; i < _toasts.Count; i++)
            {
                GUI.Box(new Rect(x, y, width, 24f), _toasts[i].Text);
                y += 26f;
            }
        }

        private void DrawPanel()
        {
            var panel = new Rect(20f, 20f, 420f, 252f);
            GUI.Box(panel, "Archipelago (F7)");

            float x = panel.x + 10f;
            float y = panel.y + 26f;
            float width = panel.width - 20f;
            float labelWidth = 80f;
            float fieldX = x + labelWidth;
            float fieldWidth = width - labelWidth;

            GUI.Label(new Rect(x, y, labelWidth, 20f), "Host");
            _hostField = GUI.TextField(new Rect(fieldX, y, fieldWidth, 20f), _hostField ?? "");
            y += 24f;

            GUI.Label(new Rect(x, y, labelWidth, 20f), "Port");
            _portField = GUI.TextField(new Rect(fieldX, y, fieldWidth, 20f), _portField ?? "");
            y += 24f;

            GUI.Label(new Rect(x, y, labelWidth, 20f), "Slot");
            _slotField = GUI.TextField(new Rect(fieldX, y, fieldWidth, 20f), _slotField ?? "");
            y += 24f;

            GUI.Label(new Rect(x, y, labelWidth, 20f), "Password");
            _passwordField = GUI.PasswordField(new Rect(fieldX, y, fieldWidth, 20f), _passwordField ?? "", '*');
            y += 28f;

            if (GUI.Button(new Rect(x, y, 92f, 24f), "Connect"))
            {
                ApplyFields();
                _client.Connect(_config.Host, _config.Port, _config.SlotName, _config.Password);
            }

            if (GUI.Button(new Rect(x + 100f, y, 92f, 24f), "Disconnect"))
            {
                _client.Disconnect();
            }

            if (GUI.Button(new Rect(x + 200f, y, 92f, 24f), "Save config"))
            {
                ApplyFields();
                _config.Save();
            }

            _config.AutoConnect = GUI.Toggle(new Rect(x + 300f, y + 3f, 100f, 20f), _config.AutoConnect, "Auto connect");
            y += 30f;

            if (GUI.Button(new Rect(x, y, 130f, 22f), _progressVisible ? "Hide progress" : "Show progress"))
            {
                _progressVisible = !_progressVisible;
            }
            y += 26f;

            GUI.Label(new Rect(x, y, width, 20f), _client.Status);
            y += 20f;

            GUI.Label(new Rect(x, y, width, 20f),
                "Checks: " + _client.LocationsChecked + "/" + _client.LocationsTotal +
                "   Items: " + _client.ItemsApplied + "/" + _client.ItemsReceived +
                (_client.DeathLinkEnabled ? "   DeathLink" : ""));
            y += 20f;

            if (Core.Store != null && Core.Store.Mismatched)
            {
                var previous = GUI.color;
                GUI.color = Color.red;
                GUI.Label(new Rect(x, y, width, 20f), "SAVE/SEED MISMATCH - items and checks disabled");
                GUI.color = previous;
            }
        }

        private void ApplyFields()
        {
            _config.Host = NormalizeHost(_hostField);
            _hostField = _config.Host;

            if (int.TryParse((_portField ?? "").Trim(), out int parsedPort) && parsedPort > 0 && parsedPort <= 65535)
            {
                _config.Port = parsedPort;
            }
            _portField = _config.Port.ToString();

            _config.SlotName = (_slotField ?? "").Trim();
            _config.Password = _passwordField ?? "";
        }

        /// <summary>Accepts a pasted "/connect archipelago.gg:38281" line as well as a bare host.</summary>
        private static string NormalizeHost(string raw)
        {
            string value = (raw ?? "").Trim();
            if (value.StartsWith(ConnectCommandPrefix, StringComparison.OrdinalIgnoreCase))
            {
                value = value.Substring(ConnectCommandPrefix.Length).Trim();
            }
            return value;
        }

        /// <summary>
        /// Secondary text channel through the cheat console, which is not debug gated.
        /// Must not be called before a scene is loaded: CheatGameHandler.TryGet dereferences the
        /// game manager and throws inside IL2CPP while the game is still bootstrapping.
        /// Returns true once the command is registered so the caller can stop retrying.
        /// </summary>
        public bool RegisterCheat()
        {
            if (_cheatRegistered)
            {
                return true;
            }

            try
            {
                // A false return means the command was queued until cheat mode is enabled, which is
                // still success from our side.
                CheatMenuAccess.RegisterCheat(
                    "ap_connect",
                    OnConnectCommand,
                    3,
                    4,
                    "ap_connect <host> <port> <slot> [password]",
                    "Connect this save to an Archipelago server");
                // maxArgs -1 is CommandTerminal's "no upper bound": the console splits on
                // whitespace, so a multi-word message arrives as one arg per word.
                CheatMenuAccess.RegisterCheat(
                    "ap_say",
                    OnSayCommand,
                    1,
                    -1,
                    "ap_say <message...>",
                    "Send chat or a server command (!hint <item>, !release, ...) to Archipelago");
                _cheatRegistered = true;
                MelonLogger.Msg("Registered the ap_connect and ap_say console commands.");
                return true;
            }
            catch (Exception e)
            {
                if (!_cheatWarned)
                {
                    _cheatWarned = true;
                    MelonLogger.Warning("ap_connect not available yet, will retry on the next scene: " + e.Message);
                }
                return false;
            }
        }

        private void OnConnectCommand(Il2CppReferenceArray<CommandArg> args)
        {
            try
            {
                string host = NormalizeHost(args[0].String);
                int port = args[1].Int;
                string slot = args[2].String;
                string password = args.Length > 3 ? args[3].String : "";

                _hostField = host;
                _portField = port.ToString();
                _slotField = slot;
                _passwordField = password;
                ApplyFields();
                _client.Connect(_config.Host, _config.Port, _config.SlotName, _config.Password);
            }
            catch (Exception e)
            {
                MelonLogger.Error("ap_connect failed: " + e);
            }
        }

        private void OnSayCommand(Il2CppReferenceArray<CommandArg> args)
        {
            try
            {
                // Rejoin what the console split on whitespace so the server sees one message.
                // Original spacing is lost, which is fine for chat and for !commands.
                string[] words = new string[args.Length];
                for (int i = 0; i < args.Length; i++)
                {
                    words[i] = args[i].String;
                }
                _client.Say(string.Join(" ", words));
            }
            catch (Exception e)
            {
                MelonLogger.Error("ap_say failed: " + e);
            }
        }
    }
}
