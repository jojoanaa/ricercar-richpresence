# Ricercar Discord Rich Presence

This Ricercar plugin publishes the track played by ricercar to Discord. It
reads ricercar's standard MPRIS interface, so it works with Qobuz and every
other Ricercar source plugin without changes to Ricercar.

It publishes:

- Listening activity with artist, title, album, cover and playback progress.
- A cleared activity while playback is paused or stopped.
- A direct track button when Ricercar exposes an HTTP(S) track URL.
- A DuckDuckGo search button for Qobuz plugin URLs.

## Installation in ricercar

1. Create a Discord application at <https://discord.com/developers/applications>
   and copy its **Application ID**.
2. Upload an image asset named `ricercar` under **Rich Presence -> Art Assets**.
3. In ricercar, open **Plugins -> Add plugin from file** and select the
   executable:

   ```sh
   ricercar-discord-presence-x86_64
   ```

4. Open the installed plugin's settings and enter your Discord **Application
   ID**. The plugin is restarted automatically after saving.

The bundled executable targets Linux x86_64. It includes all Python
dependencies; no separate virtual environment is needed. The Application ID
is intentionally not included in this repository.

## Build the plugin

Install Python 3.10 or newer and build dependencies, then run:

```sh
python -m venv .venv
.venv/bin/pip install . pyinstaller
.venv/bin/pyinstaller --onefile --clean --name ricercar-discord-presence \
   ricercar_discord_presence.py
```

The resulting `dist/ricercar-discord-presence` file can be added to ricercar.
The repository also includes the ready-to-use
`ricercar-discord-presence-x86_64` release binary.

## Ricercar compatibility

The plugin speaks Ricercar plugin protocol 1 over newline-delimited JSON-RPC.
It declares no catalogue capabilities, keeps protocol traffic on stdout, and
writes diagnostics to stderr. The Discord Application ID is provided through
Ricercar's plugin settings and is never passed on a command line.

## Development run

To run the Python version directly while developing:

   ```sh
   cd discord-rich-presence
   python -m venv ~/.local/share/ricercar-discord-presence/.venv
   ~/.local/share/ricercar-discord-presence/.venv/bin/pip install .
   DISCORD_CLIENT_ID=your-application-id \
     ~/.local/share/ricercar-discord-presence/.venv/bin/ricercar-discord-presence
   ```

The plugin clears the Discord activity when playback stops or pauses. While
playing, it publishes the track, artist, album, progress and cover.

Discord controls which parts of a Rich Presence are clickable. The cover and
title URL fields are provided when possible, and the action button is retained
as a fallback. Discord may hide buttons in compact activity views.