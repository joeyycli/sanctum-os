#!/usr/bin/env python3
# Sanctum Assistant — the built-in, security-conscious desktop agent for Sanctum OS.
#
# Two brains, one interface:
#   * An offline command parser handles the common verbs (open an app, go to a
#     site, search YouTube/web, volume, light/dark, lock, settings) instantly,
#     with no network and no API key.
#   * When an Anthropic API key is present, freeform or multi-step requests are
#     handed to Claude, which drives the SAME allowlisted actions via tool use.
#
# Capability posture (matches the OS): every action is an allowlisted verb.
# The one open-ended verb — running a shell command — always asks first.
#
# No third-party Python deps: GTK4/Libadwaita via PyGObject, Anthropic via urllib.

import json
import os
import re
import threading
import urllib.request
import urllib.error
from urllib.parse import quote_plus

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, Gdk, Pango  # noqa: E402

APP_ID = "os.sanctum.Assistant"
CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "sanctum-assistant")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_MODEL = "claude-sonnet-5"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Known apps -> freedesktop desktop-ids as installed by Sanctum OS.
APP_ALIASES = {
    "firefox": "org.mozilla.firefox.desktop",
    "browser": "org.mozilla.firefox.desktop",
    "telegram": "org.telegram.desktop.desktop",
    "claude": "com.anthropic.Claude.desktop",
    "claude desktop": "com.anthropic.Claude.desktop",
    "terminal": "org.gnome.Console.desktop",
    "console": "org.gnome.Console.desktop",
    "files": "org.gnome.Nautilus.desktop",
    "nautilus": "org.gnome.Nautilus.desktop",
    "file manager": "org.gnome.Nautilus.desktop",
    "settings": "org.gnome.Settings.desktop",
    "control center": "org.gnome.Settings.desktop",
}

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={}",
    "duckduckgo": "https://duckduckgo.com/?q={}",
    "ddg": "https://duckduckgo.com/?q={}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={}",
    "youtube": "https://www.youtube.com/results?search_query={}",
}


# --------------------------------------------------------------------------- #
#  Actions — the allowlist. Each returns a short human-readable status string.
# --------------------------------------------------------------------------- #
class Actions:
    def launch_app(self, name):
        name = name.strip().lower()
        did = APP_ALIASES.get(name)
        if did:
            info = Gio.DesktopAppInfo.new(did)
            if info:
                info.launch([], None)
                return f"Opening {info.get_display_name()}."
        for ai in Gio.AppInfo.get_all():
            if name in ai.get_display_name().lower():
                ai.launch([], None)
                return f"Opening {ai.get_display_name()}."
        return f"I couldn't find an app called “{name}”."

    def open_url(self, url):
        url = url.strip()
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
            url = "https://" + url
        Gio.AppInfo.launch_default_for_uri(url, None)
        return f"Opening {url}"

    def web_search(self, query, engine="duckduckgo"):
        tmpl = SEARCH_ENGINES.get(engine, SEARCH_ENGINES["duckduckgo"])
        Gio.AppInfo.launch_default_for_uri(tmpl.format(quote_plus(query)), None)
        where = "YouTube" if engine == "youtube" else engine.capitalize()
        return f"Searching {where} for “{query}”."

    def set_volume(self, action, value=None):
        sink = "@DEFAULT_AUDIO_SINK@"
        if action == "mute":
            arg = ["set-mute", sink, "1"]; msg = "Muted."
        elif action == "unmute":
            arg = ["set-mute", sink, "0"]; msg = "Unmuted."
        elif action == "up":
            arg = ["set-volume", sink, "5%+"]; msg = "Volume up."
        elif action == "down":
            arg = ["set-volume", sink, "5%-"]; msg = "Volume down."
        elif action == "set" and value is not None:
            arg = ["set-volume", sink, f"{max(0, min(150, int(value)))}%"]
            msg = f"Volume set to {value}%."
        else:
            return "I didn't catch the volume change."
        try:
            Gio.Subprocess.new(["wpctl"] + arg, Gio.SubprocessFlags.STDERR_SILENCE)
            return msg
        except GLib.Error:
            return "Couldn't reach the audio system."

    def set_color_scheme(self, mode):
        s = Gio.Settings.new("org.gnome.desktop.interface")
        s.set_string("color-scheme",
                     "prefer-dark" if mode == "dark" else "default")
        return f"Switched to {mode} mode."

    def lock_screen(self):
        try:
            Gio.Subprocess.new(["loginctl", "lock-session"],
                               Gio.SubprocessFlags.STDERR_SILENCE)
            return "Locking the screen."
        except GLib.Error:
            return "Couldn't lock the screen."

    def system_info(self):
        try:
            with open("/proc/loadavg") as f:
                load = f.read().split()[:3]
            with open("/proc/meminfo") as f:
                mem = {}
                for line in f:
                    k, _, v = line.partition(":")
                    mem[k] = v.strip()
            total = int(mem["MemTotal"].split()[0]) // 1024
            avail = int(mem["MemAvailable"].split()[0]) // 1024
            host = GLib.get_host_name()
            return (f"{host}: load {'/'.join(load)}, "
                    f"memory {total - avail} of {total} MiB in use.")
        except Exception:
            return "Couldn't read system status."

    def run_shell(self, command):
        # Executed only after the UI has confirmed with the user.
        try:
            proc = Gio.Subprocess.new(
                ["/bin/sh", "-c", command],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
            ok, out, _ = proc.communicate_utf8(None, None)
            out = (out or "").strip()
            return out if out else "(command finished with no output)"
        except GLib.Error as e:
            return f"Command failed: {e.message}"


# --------------------------------------------------------------------------- #
#  Offline parser — maps plain-language commands to (action, kwargs) tuples.
#  Returns a list of steps, or None if nothing matched (→ hand to the LLM).
# --------------------------------------------------------------------------- #
class Parser:
    APP_VERBS = r"(?:open|launch|start|run|fire up)"
    NAV_VERBS = r"(?:go to|goto|visit|navigate to|browse to|open)"

    def parse(self, text):
        text = text.strip()
        clauses = self._split(text)
        steps = []
        for clause in clauses:
            step = self._parse_one(clause)
            if step is None:
                return None  # any unparsable clause → whole thing goes to LLM
            steps.append(step)
        return steps or None

    def _split(self, text):
        # Split compound commands on " and then " / ", then " / " and " —
        # but only where the following clause begins with a known verb, so
        # "rock and roll" stays intact.
        parts = re.split(r"\s*(?:,?\s*and then\s+|,\s*then\s+|\s+and\s+)", text,
                         flags=re.IGNORECASE)
        if len(parts) == 1:
            return parts
        merged, buf = [], ""
        starter = re.compile(
            rf"^\s*(?:{self.APP_VERBS}|{self.NAV_VERBS}|search|play|find|"
            r"volume|mute|unmute|turn|set|lock|dark|light|what|show)\b",
            re.IGNORECASE)
        for p in parts:
            if buf and not starter.match(p):
                buf += " and " + p
            else:
                if buf:
                    merged.append(buf)
                buf = p
        if buf:
            merged.append(buf)
        return merged

    def _parse_one(self, c):
        s = c.strip()
        low = s.lower()

        # "<something> on youtube"  /  "play|search <q> on youtube"
        m = re.search(r"^(?:play|search|find|go to|open|watch)?\s*(.+?)\s+on\s+youtube$",
                      low)
        if m:
            q = self._strip_arg(s, m.group(1))
            return ("web_search", {"query": q, "engine": "youtube"})

        # "search <q> on wikipedia/google/ddg"  or  "search [for] <q>"
        m = re.search(r"^(?:search|find|look up)\s+(?:for\s+)?(.+?)"
                      r"(?:\s+on\s+(google|duckduckgo|ddg|wikipedia|youtube))?$", low)
        if m:
            q = self._strip_arg(s, m.group(1))
            engine = m.group(2) or "duckduckgo"
            return ("web_search", {"query": q, "engine": engine})

        # volume
        if re.search(r"\b(mute)\b", low) and "unmute" not in low:
            return ("set_volume", {"action": "mute"})
        if "unmute" in low:
            return ("set_volume", {"action": "unmute"})
        m = re.search(r"volume\s+(?:to\s+)?(\d{1,3})", low)
        if m:
            return ("set_volume", {"action": "set", "value": int(m.group(1))})
        if re.search(r"(volume up|louder|turn (?:it |the volume )?up)", low):
            return ("set_volume", {"action": "up"})
        if re.search(r"(volume down|quieter|turn (?:it |the volume )?down)", low):
            return ("set_volume", {"action": "down"})

        # appearance
        if re.search(r"\b(dark mode|dark theme|go dark)\b", low):
            return ("set_color_scheme", {"mode": "dark"})
        if re.search(r"\b(light mode|light theme|go light)\b", low):
            return ("set_color_scheme", {"mode": "light"})

        # lock
        if re.search(r"\block(?:\s+(?:the\s+)?screen)?\b", low):
            return ("lock_screen", {})

        # system status
        if re.search(r"(system (?:status|info)|how('| i)?s the system|"
                     r"memory usage|resource usage)", low):
            return ("system_info", {})

        # navigate: "go to <url or site>"
        m = re.search(rf"^{self.NAV_VERBS}\s+(.+)$", low)
        if m:
            arg = self._strip_arg(s, m.group(1))
            if self._looks_like_url(arg):
                return ("open_url", {"url": arg})
            # "open <known app>"
            if arg.lower() in APP_ALIASES:
                return ("launch_app", {"name": arg})
            return ("web_search", {"query": arg, "engine": "duckduckgo"})

        # launch: "open/launch/start <app>"
        m = re.search(rf"^{self.APP_VERBS}\s+(.+)$", low)
        if m:
            arg = self._strip_arg(s, m.group(1))
            if self._looks_like_url(arg):
                return ("open_url", {"url": arg})
            return ("launch_app", {"name": re.sub(r"^(the|my)\s+", "", arg)})

        return None

    @staticmethod
    def _strip_arg(original, lowered_fragment):
        # Recover original-case text for the matched fragment.
        idx = original.lower().find(lowered_fragment)
        return original[idx:idx + len(lowered_fragment)].strip() if idx >= 0 \
            else lowered_fragment.strip()

    @staticmethod
    def _looks_like_url(s):
        s = s.strip()
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", s):
            return True
        return bool(re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", s))


# --------------------------------------------------------------------------- #
#  Claude tool bridge — the same actions, exposed to the API as tools.
# --------------------------------------------------------------------------- #
TOOLS = [
    {"name": "launch_app",
     "description": "Open an installed application by name (e.g. firefox, "
                    "telegram, claude, terminal, files, settings).",
     "input_schema": {"type": "object",
                      "properties": {"name": {"type": "string"}},
                      "required": ["name"]}},
    {"name": "open_url",
     "description": "Open a web address in the default browser (Firefox).",
     "input_schema": {"type": "object",
                      "properties": {"url": {"type": "string"}},
                      "required": ["url"]}},
    {"name": "web_search",
     "description": "Search the web or a specific site and open the results in "
                    "Firefox.",
     "input_schema": {"type": "object",
                      "properties": {
                          "query": {"type": "string"},
                          "engine": {"type": "string",
                                     "enum": list(SEARCH_ENGINES.keys())}},
                      "required": ["query"]}},
    {"name": "set_volume",
     "description": "Adjust system volume.",
     "input_schema": {"type": "object",
                      "properties": {
                          "action": {"type": "string",
                                     "enum": ["up", "down", "mute", "unmute", "set"]},
                          "value": {"type": "integer"}},
                      "required": ["action"]}},
    {"name": "set_color_scheme",
     "description": "Switch the desktop between light and dark mode.",
     "input_schema": {"type": "object",
                      "properties": {"mode": {"type": "string",
                                              "enum": ["light", "dark"]}},
                      "required": ["mode"]}},
    {"name": "lock_screen",
     "description": "Lock the screen.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "system_info",
     "description": "Report host name, load average and memory usage.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_shell",
     "description": "Run a shell command. The user is asked to confirm every "
                    "command before it runs, so use this for things the other "
                    "tools cannot do.",
     "input_schema": {"type": "object",
                      "properties": {"command": {"type": "string"}},
                      "required": ["command"]}},
]

SYSTEM_PROMPT = (
    "You are Sanctum Assistant, the built-in agent for Sanctum OS, a hardened, "
    "minimal, privacy-first Debian derivative for secure AI work. You help the "
    "user operate their computer through the provided tools. Be concise and "
    "act rather than explain: when the user asks to open, search, play, or "
    "change something, call the appropriate tool. Only the installed apps exist "
    "(Claude Desktop, Firefox, Telegram, a terminal, Files, Settings). Prefer "
    "the specific tools; use run_shell only when nothing else fits — the user "
    "must approve each shell command, so keep them minimal and safe. After "
    "acting, confirm briefly in one sentence."
)


class Claude:
    def __init__(self, api_key, model):
        self.api_key = api_key
        self.model = model

    def _post(self, messages):
        body = json.dumps({
            "model": self.model,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "tools": TOOLS,
            "messages": messages,
        }).encode()
        req = urllib.request.Request(ANTHROPIC_URL, data=body, method="POST")
        req.add_header("x-api-key", self.api_key)
        req.add_header("anthropic-version", ANTHROPIC_VERSION)
        req.add_header("content-type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    def run(self, prompt, execute_tool, max_turns=6):
        """Agent loop. execute_tool(name, input) -> str. Returns final text."""
        messages = [{"role": "user", "content": prompt}]
        for _ in range(max_turns):
            resp = self._post(messages)
            content = resp.get("content", [])
            messages.append({"role": "assistant", "content": content})
            tool_uses = [b for b in content if b.get("type") == "tool_use"]
            if not tool_uses:
                return "".join(b.get("text", "") for b in content
                               if b.get("type") == "text").strip() or "Done."
            results = []
            for tu in tool_uses:
                out = execute_tool(tu["name"], tu.get("input", {}))
                results.append({"type": "tool_result",
                                "tool_use_id": tu["id"],
                                "content": out})
            messages.append({"role": "user", "content": results})
        return "I stopped after several steps to avoid looping."


# --------------------------------------------------------------------------- #
#  UI
# --------------------------------------------------------------------------- #
CSS = b"""
.bubble { border-radius: 14px; padding: 10px 14px; margin: 3px 2px; }
.bubble-user { background: #5C6F8A; color: #ffffff; }
.bubble-assistant { background: alpha(#1A1A1E, 0.06); color: #1A1A1E; }
.bubble-note { color: #6E6E76; font-size: 0.9em; }
.greeting { color: #6E6E76; }
entry.prompt { border-radius: 12px; padding: 8px 12px; }
"""


class AssistantWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Sanctum Assistant")
        self.set_default_size(560, 640)
        self.actions = Actions()
        self.parser = Parser()

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        menu = Gio.Menu()
        menu.append("Set Claude API key…", "win.setkey")
        menu.append("About", "win.about")
        btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(btn)
        toolbar.add_top_bar(header)

        self.scroller = Gtk.ScrolledWindow(vexpand=True)
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.log = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                           margin_start=12, margin_end=12,
                           margin_top=12, margin_bottom=12)
        self.scroller.set_child(self.log)

        self.entry = Gtk.Entry(placeholder_text="Ask Sanctum…  (e.g. open firefox and go to lospollostv on youtube)",
                               margin_start=12, margin_end=12,
                               margin_top=6, margin_bottom=12)
        self.entry.add_css_class("prompt")
        self.entry.connect("activate", self.on_submit)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.scroller)
        box.append(self.entry)
        toolbar.set_content(box)
        self.set_content(toolbar)

        self._install_actions()
        self._greeting()
        self.entry.grab_focus()

    def _install_actions(self):
        a = Gio.SimpleAction.new("setkey", None)
        a.connect("activate", self.on_setkey)
        self.add_action(a)
        b = Gio.SimpleAction.new("about", None)
        b.connect("activate", self.on_about)
        self.add_action(b)

    def _greeting(self):
        cfg = load_config()
        brain = "Claude-powered" if cfg.get("api_key") else "offline"
        lbl = Gtk.Label(xalign=0, wrap=True)
        lbl.add_css_class("greeting")
        lbl.set_text(
            "Sanctum Assistant — tell me what to do.\n"
            "Try: “open firefox and go to lospollostv on youtube”, "
            "“search quiet mechanical keyboards”, “dark mode”, "
            "“lock the screen”.\n"
            f"Brain: {brain}." +
            ("" if cfg.get("api_key") else
             "  Add a Claude API key in the menu for freeform requests."))
        self.log.append(lbl)

    # ---- message plumbing ------------------------------------------------- #
    def add_bubble(self, text, kind):
        row = Gtk.Box(halign=Gtk.Align.END if kind == "user" else Gtk.Align.START)
        lbl = Gtk.Label(label=text, wrap=True, xalign=0, selectable=True,
                        max_width_chars=48)
        lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        lbl.add_css_class("bubble")
        lbl.add_css_class(f"bubble-{kind}")
        row.append(lbl)
        self.log.append(row)
        GLib.idle_add(self._scroll_end)
        return lbl

    def _scroll_end(self):
        adj = self.scroller.get_vadjustment()
        adj.set_value(adj.get_upper())
        return False

    def on_submit(self, _entry):
        text = self.entry.get_text().strip()
        if not text:
            return
        self.entry.set_text("")
        self.add_bubble(text, "user")
        steps = self.parser.parse(text)
        if steps is not None:
            self._run_steps(steps)
            return
        cfg = load_config()
        if cfg.get("api_key"):
            pending = self.add_bubble("Thinking…", "assistant")
            threading.Thread(target=self._llm_worker,
                             args=(text, cfg, pending), daemon=True).start()
        else:
            self.add_bubble(
                "I didn't recognise that as a direct command, and no Claude API "
                "key is set. Add one from the menu to enable freeform requests, "
                "or try a direct command like “open firefox” or "
                "“search cats on youtube”.", "assistant")

    def _run_steps(self, steps):
        for name, kwargs in steps:
            if name == "run_shell":
                self._confirm_and_run(kwargs.get("command", ""))
            else:
                self.add_bubble(getattr(self.actions, name)(**kwargs),
                                "assistant")

    # ---- LLM path --------------------------------------------------------- #
    def _llm_worker(self, text, cfg, pending):
        claude = Claude(cfg["api_key"], cfg.get("model", DEFAULT_MODEL))
        try:
            final = claude.run(text, self._exec_tool_blocking)
        except urllib.error.HTTPError as e:
            final = f"Claude API error ({e.code}). Check your API key in the menu."
        except Exception as e:  # noqa: BLE001
            final = f"Couldn't reach Claude: {e}"
        GLib.idle_add(pending.set_text, final)
        GLib.idle_add(self._scroll_end)

    def _exec_tool_blocking(self, name, tool_input):
        # Runs inside the worker thread. Non-shell actions are quick and
        # thread-safe (Gio); shell needs a marshaled confirmation.
        if name == "run_shell":
            cmd = tool_input.get("command", "")
            if not self._confirm_blocking(cmd):
                return "User declined to run the command."
            return self.actions.run_shell(cmd)
        fn = getattr(self.actions, name, None)
        if not fn:
            return f"Unknown tool {name}."
        try:
            return fn(**tool_input)
        except Exception as e:  # noqa: BLE001
            return f"Tool error: {e}"

    # ---- confirmed shell -------------------------------------------------- #
    def _confirm_and_run(self, command):
        dlg = self._shell_dialog(command)
        dlg.connect("response", self._on_confirm_response)
        dlg.present()

    def _on_confirm_response(self, dlg, response):
        if response == "run":
            self.add_bubble(self.actions.run_shell(self._pending_cmd),
                            "assistant")

    def _shell_dialog(self, command):
        self._pending_cmd = command
        dlg = Adw.MessageDialog(transient_for=self, modal=True,
                                heading="Run this command?",
                                body=command)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("run", "Run")
        dlg.set_response_appearance("run", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        return dlg

    def _confirm_blocking(self, command):
        ev = threading.Event()
        holder = {"ok": False}

        def ask():
            dlg = Adw.MessageDialog(transient_for=self, modal=True,
                                    heading="Run this command?", body=command)
            dlg.add_response("cancel", "Cancel")
            dlg.add_response("run", "Run")
            dlg.set_response_appearance("run", Adw.ResponseAppearance.SUGGESTED)

            def done(_d, r):
                holder["ok"] = (r == "run")
                ev.set()
            dlg.connect("response", done)
            dlg.present()
        GLib.idle_add(ask)
        ev.wait()
        return holder["ok"]

    # ---- menu actions ----------------------------------------------------- #
    def on_setkey(self, *_):
        dlg = Adw.MessageDialog(transient_for=self, modal=True,
                                heading="Claude API key",
                                body="Paste your Anthropic API key. It is stored "
                                     "locally at ~/.config/sanctum-assistant/"
                                     "config.json and sent only to api.anthropic.com.")
        entry = Gtk.Entry(visibility=False,
                          placeholder_text="sk-ant-…")
        cfg = load_config()
        if cfg.get("api_key"):
            entry.set_text(cfg["api_key"])
        dlg.set_extra_child(entry)
        dlg.add_response("cancel", "Cancel")
        dlg.add_response("save", "Save")
        dlg.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def done(_d, r):
            if r == "save":
                c = load_config()
                c["api_key"] = entry.get_text().strip()
                c.setdefault("model", DEFAULT_MODEL)
                save_config(c)
                self.add_bubble("API key saved. Freeform requests are now "
                                "handled by Claude.", "assistant")
        dlg.connect("response", done)
        dlg.present()

    def on_about(self, *_):
        about = Adw.AboutWindow(
            transient_for=self, application_name="Sanctum Assistant",
            application_icon="sanctum", version="1.0",
            developer_name="Sanctum OS",
            comments="The built-in desktop agent for Sanctum OS.",
            license_type=Gtk.License.MIT_X11)
        about.present()


def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"model": DEFAULT_MODEL}


def save_config(cfg):
    os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
    fd = os.open(CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=2)


class AssistantApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_startup(self):
        Adw.Application.do_startup(self)
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def do_activate(self):
        win = self.props.active_window or AssistantWindow(self)
        win.present()


def main():
    return AssistantApp().run(None)


if __name__ == "__main__":
    raise SystemExit(main())
