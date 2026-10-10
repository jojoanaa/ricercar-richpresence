"""Publish ricercar's MPRIS metadata as Discord Rich Presence."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType
from dbus_next.errors import DBusError
from pypresence import ActivityType, Presence
from pypresence.exceptions import DiscordError, InvalidID, PipeClosed

LOG = logging.getLogger("ricercar-discord-presence")
BUS_NAME = "org.mpris.MediaPlayer2.ricercar"
OBJECT_PATH = "/org/mpris/MediaPlayer2"
PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
PLUGIN_ID = "ricercar-discord-presence"
PLUGIN_VERSION = "0.2.1"


@dataclass(frozen=True)
class Track:
    title: str
    artist: str
    album: str
    art_url: str
    track_url: str
    duration_us: int
    position_us: int


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def track_from_metadata(metadata: dict[str, Any], position_us: int = 0) -> Track:
    """Convert MPRIS variants into the small model used by the publisher."""
    artist = _value(metadata.get("xesam:artist", ["Unknown artist"]))
    if isinstance(artist, (list, tuple)):
        artist = ", ".join(str(item) for item in artist)
    return Track(
        title=str(_value(metadata.get("xesam:title", "Unknown track"))),
        artist=str(artist),
        album=str(_value(metadata.get("xesam:album", ""))),
        art_url=str(_value(metadata.get("mpris:artUrl", ""))),
        track_url=str(_value(metadata.get("xesam:url", ""))),
        duration_us=int(_value(metadata.get("mpris:length", 0))),
        position_us=max(0, position_us),
    )


class Publisher:
    def __init__(self, client_id: str, image_key: str) -> None:
        self._rpc = Presence(client_id)
        self._image_key = image_key
        self._connected = False

    def close(self) -> None:
        if self._connected:
            try:
                self._rpc.close()
            except (DiscordError, OSError, PipeClosed):
                pass
            finally:
                self._connected = False

    def update(self, status: str, track: Track | None) -> None:
        if status in ("Stopped", "Paused") or track is None or not track.title:
            self._clear()
            return
        self._ensure_connected()
        details = track.title[:128]
        state = track.artist[:128]
        image = track.art_url if track.art_url.startswith(("http://", "https://")) else self._image_key
        query = quote(f"{track.title} - {track.artist} - Qobuz")
        search_url = f"https://duckduckgo.com/?q={query}"
        kwargs: dict[str, Any] = {
            "activity_type": ActivityType.LISTENING,
            "name": f"{track.artist} - {track.title}"[:128],
            "details": details,
            "details_url": search_url,
            "state": state,
            "large_image": image,
            "large_text": track.album[:128] or "ricercar",
            "large_url": search_url,
        }
        if track.track_url.startswith(("http://", "https://")):
            kwargs["buttons"] = [{"label": "Open track", "url": track.track_url}]
        else:
            kwargs["buttons"] = [{
                "label": "Open DuckDuckGo",
                "url": search_url,
            }]
        if status == "Playing" and track.duration_us > 0:
            now = int(time.time())
            offset = track.position_us // 1_000_000
            duration = track.duration_us // 1_000_000
            kwargs["start"] = now - offset
            kwargs["end"] = now - offset + duration
        try:
            self._rpc.update(**kwargs)
        except DiscordError:
            if image == self._image_key:
                raise
            kwargs["large_image"] = self._image_key
            self._rpc.update(**kwargs)

    def _ensure_connected(self) -> None:
        if self._connected:
            return
        self._rpc.connect()
        self._connected = True

    def _clear(self) -> None:
        if not self._connected:
            return
        self._rpc.clear()


async def read_player(bus: MessageBus) -> tuple[str, Track | None]:
    introspection = await bus.introspect(BUS_NAME, OBJECT_PATH)
    proxy = bus.get_proxy_object(BUS_NAME, OBJECT_PATH, introspection)
    props = proxy.get_interface("org.freedesktop.DBus.Properties")
    values = await props.call_get_all(PLAYER_INTERFACE)
    status = str(_value(values.get("PlaybackStatus", "Stopped")))
    metadata = _value(values.get("Metadata", {}))
    position = int(_value(values.get("Position", 0)))
    return status, track_from_metadata(metadata, position) if metadata else None


async def run(client_id: str, image_key: str, interval: float) -> None:
    publisher = Publisher(client_id, image_key)
    bus: MessageBus | None = None
    last: tuple[str, Track | None] | None = None
    try:
        while True:
            try:
                if bus is None:
                    bus = await MessageBus(bus_type=BusType.SESSION).connect()
                current = await read_player(bus)
                if current != last or current[0] == "Playing":
                    await asyncio.to_thread(publisher.update, *current)
                    last = current
            except (DBusError, FileNotFoundError, ConnectionError, asyncio.TimeoutError) as error:
                LOG.debug("ricercar is not available yet: %s", error)
                if bus is not None:
                    bus.disconnect()
                    bus = None
            except (DiscordError, InvalidID, PipeClosed, OSError) as error:
                LOG.warning("Discord connection unavailable: %s", error)
                publisher.close()
            await asyncio.sleep(interval)
    finally:
        publisher.close()
        if bus is not None:
            bus.disconnect()


async def _read_line() -> str:
    return await asyncio.to_thread(sys.stdin.readline)


def _send_rpc(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


async def run_as_ricercar_plugin() -> None:
    """Serve Ricercar's JSON-RPC lifecycle while publishing MPRIS playback."""
    line = await _read_line()
    if not line:
        return
    request = json.loads(line)
    params = request.get("params", {})
    settings = params.get("settings", {})
    _send_rpc({
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": {
            "protocol": 1,
            "plugin": {
                "id": PLUGIN_ID,
                "name": "Ricercar Discord Rich Presence",
                "version": PLUGIN_VERSION,
            },
            "capabilities": {},
            "settings": [{
                "key": "client_id",
                "type": "string",
                "section": "Discord",
                "label": "Discord Application ID",
                "description": "Application ID from the Discord Developer Portal.",
                "placeholder": "Your Discord Application ID",
                "max_length": 32,
                "restart": True,
                "default": "",
            }],
        },
    })
    client_id = str(settings.get("client_id", ""))
    presence_task = (
        asyncio.create_task(run(client_id, "ricercar", 5.0)) if client_id else None
    )
    try:
        while True:
            line = await _read_line()
            if not line:
                break
            message = json.loads(line)
            method = message.get("method")
            if method == "shutdown":
                if "id" in message:
                    _send_rpc({"jsonrpc": "2.0", "id": message["id"], "result": None})
                break
            if method == "settings.changed":
                continue
            if "id" in message:
                _send_rpc({
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32601, "message": "Method not found"},
                })
    finally:
        if presence_task is not None:
            presence_task.cancel()
            await asyncio.gather(presence_task, return_exceptions=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--client-id",
        default=os.environ.get("DISCORD_CLIENT_ID"),
        help="Discord application client ID (or DISCORD_CLIENT_ID)",
    )
    parser.add_argument(
        "--image-key",
        default=os.environ.get("DISCORD_IMAGE_KEY", "ricercar"),
        help="Name of the large image asset in the Discord application",
    )
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if not args.client_id and not sys.stdin.isatty():
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
        asyncio.run(run_as_ricercar_plugin())
        return
    if not args.client_id:
        parser.error("--client-id or DISCORD_CLIENT_ID is required")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    try:
        asyncio.run(run(args.client_id, args.image_key, max(1.0, args.interval)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()