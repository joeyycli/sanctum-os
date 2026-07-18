# Sanctum Assistant

A built-in desktop agent. Press **Super+A** (or click it in the dock) and tell
your computer what to do in plain language.

## Two brains

- **Offline parser** (always on, no key, no network): handles the common verbs
  instantly — launch apps, open sites, search YouTube/web/Wikipedia, adjust
  volume, toggle light/dark, lock the screen, report system status.
- **Claude** (optional): add an Anthropic API key from the menu (**⋮ → Set
  Claude API key**) and any request the parser doesn't recognise is handed to
  Claude, which drives the same actions via tool use. The key is stored at
  `~/.config/sanctum-assistant/config.json` (mode 0600) and sent only to
  `api.anthropic.com`. Default model: `claude-sonnet-5` (editable in the file).

## Capabilities (allowlisted)

| Verb | Example |
| ---- | ------- |
| Launch an app | `open firefox`, `launch telegram`, `start claude` |
| Open a site | `go to github.com` |
| Search | `search quiet keyboards`, `lospollostv on youtube`, `search apollo on wikipedia` |
| Volume | `volume up`, `set volume to 30`, `mute` |
| Appearance | `dark mode`, `light mode` |
| Session | `lock the screen` |
| Status | `system status` |
| Shell | anything else via Claude → **each command is confirmed before it runs** |

Compound commands work: `open firefox and go to lospollostv on youtube`.

## Security

Every action is an allowlisted verb. The single open-ended capability —
running a shell command — always shows the exact command and waits for your
approval. The assistant injects no input into other apps and never reads the
screen; it is an ordinary user-session app, consistent with the OS's
Wayland/no-input-injection posture. For full screenshot-and-click control,
see the note in `docs/SECURITY.md` on why that is deliberately not shipped.
