"""Read and control Windows "Now Playing" (Spotify, YouTube in the browser, VLC, ...).

Uses the Global System Media Transport Controls API through the pywinrt packages (winrt-*).
On non-Windows systems or without the packages the module simply stays inactive.
"""
import asyncio
import base64
import logging
import threading
import time

log = logging.getLogger("skerry")


class MediaWatcher:
    def __init__(self, interval=1.0):
        self._interval = interval
        self._loop = None
        self._mgr = None
        self._state = None
        self._thumb = None
        self._thumb_key = None
        self._thumb_id = 0
        self.available = False
        self._err_logged = False

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="skerry-media").start()

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self):
        try:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as Manager,
                GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
            )
        except Exception:
            log.info("API media di Windows non disponibili")
            return
        self._Status = Status
        self._mgr = await Manager.request_async()
        self.available = True
        while True:
            try:
                await self._poll()
            except Exception:
                self._state = None
                if not self._err_logged:
                    self._err_logged = True
                    log.exception("Lettura media non riuscita")
            await asyncio.sleep(self._interval)

    async def _poll(self):
        s = self._mgr.get_current_session()
        if s is None:
            self._state = None
            return
        props = await s.try_get_media_properties_async()
        info = s.get_playback_info()
        tl = s.get_timeline_properties()
        playing = info.playback_status == self._Status.PLAYING

        def secs(v):
            try:
                return float(v.total_seconds())
            except Exception:
                return 0.0

        try:
            updated = tl.last_updated_time.timestamp()
        except Exception:
            updated = time.time()

        key = (props.title, props.artist)
        if key != self._thumb_key:
            self._thumb = await self._read_thumb(props.thumbnail)
            self._thumb_id += 1
            # the cover can arrive after the title: retry until it is there
            self._thumb_key = key if self._thumb else None

        self._state = {
            "title": props.title or "",
            "artist": props.artist or props.album_artist or "",
            "app": (s.source_app_user_model_id or "").split("!")[-1].replace(".exe", ""),
            "playing": playing,
            "position": secs(tl.position),
            "duration": secs(tl.end_time),
            "updated": updated,
            "thumb_id": self._thumb_id if self._thumb else 0,
        }

    async def _read_thumb(self, ref):
        if ref is None:
            return None
        try:
            from winrt.windows.storage.streams import Buffer, DataReader, InputStreamOptions
            stream = await ref.open_read_async()
            size = int(stream.size)
            if not size or size > 5_000_000:
                return None
            buf = Buffer(size)
            await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)
            try:
                data = bytes(buf)
            except Exception:
                reader = DataReader.from_buffer(buf)
                arr = bytearray(buf.length)
                reader.read_bytes(arr)
                data = bytes(arr)
            mime = getattr(stream, "content_type", "") or "image/png"
            return f"data:{mime};base64,{base64.b64encode(data).decode()}"
        except Exception:
            return None

    # ---------- public API ----------
    def public_state(self):
        return self._state

    def thumb(self):
        return self._thumb

    def command(self, cmd):
        if not self._mgr or not self._loop:
            return False

        async def run():
            s = self._mgr.get_current_session()
            if s is None:
                return
            if cmd == "toggle":
                await s.try_toggle_play_pause_async()
            elif cmd == "next":
                await s.try_skip_next_async()
            elif cmd == "prev":
                await s.try_skip_previous_async()
            elif isinstance(cmd, tuple) and cmd[0] == "seek":
                await s.try_change_playback_position_async(int(max(0, cmd[1]) * 10_000_000))

        fut = asyncio.run_coroutine_threadsafe(run(), self._loop)
        fut.add_done_callback(lambda f: f.exception() and log.warning("Comando media %s: %s", cmd, f.exception()))
        return True

    def seek(self, seconds):
        return self.command(("seek", float(seconds)))
