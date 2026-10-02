"""Loopback HLS relay used for protected live streams.

FFmpeg reads only a loopback URL.  This relay fetches public HLS playlists and
segments with the required browser headers, rewrites every nested URI through
itself, and validates each upstream URL.  When a licensed CDN is geo-blocked
from the hosting network, the relay can select a short-lived public Indian
HTTPS tunnel from a frequently refreshed list.  TLS remains end-to-end between
this process and the CDN; the tunnel never receives plaintext headers/media.
"""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import logging
import re
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, Optional

import aiohttp
from aiohttp import web
from pytgcalls.types import MediaStream
from pytgcalls.types.raw import Stream as RawStream
from pytgcalls.types.stream import AudioQuality, VideoQuality

from anony.core.live import LiveResolveError, _validate_public_url

log = logging.getLogger(__name__)

_MAX_PLAYLIST = 2_000_000
_MAX_REDIRECTS = 5
_PROXY_PROBE_LIMIT = 40
_PROXY_WANTED = 3
_PROXY_LIST_URL = (
    "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/"
    "proxies/countries/in/http/data.txt"
)
_BLOCKED_STATUSES = {403, 407, 429, 451, 502, 503, 504}
_URI_ATTRIBUTE = re.compile(r'URI="([^"]+)"')
_RECONNECT_OPTIONS = (
    "-reconnect 1 ",
    "-reconnect_at_eof 1 ",
    "-reconnect_streamed 1 ",
    "-reconnect_delay_max 2 ",
)


def build_live_raw_stream(url: str, video: bool, seek: int = 0) -> RawStream:
    """Build a live raw stream without PyTgCalls' VOD reconnect flags.

    ``MediaStream`` adds ``-reconnect_at_eof`` to every HTTP input before it
    knows the input is live.  Against a loopback HLS manifest that makes
    FFmpeg reconnect to the completed master response forever, so it never
    advances to media segments and Telegram receives silence.  The raw stream
    intentionally skips ffprobe and removes only those VOD reconnect options.
    """
    media = MediaStream(
        url,
        audio_parameters=AudioQuality.HIGH,
        video_parameters=VideoQuality.SD_360p,
        audio_path=url,
        audio_flags=MediaStream.Flags.AUTO_DETECT,
        video_flags=(MediaStream.Flags.AUTO_DETECT if video else MediaStream.Flags.IGNORE),
        headers=None,
        ffmpeg_parameters=f"-ss {int(seek)}" if seek > 0 else None,
    )
    for output in (media.microphone, media.camera):
        if output is None or not getattr(output, "path", None):
            continue
        command = output.path
        for option in _RECONNECT_OPTIONS:
            command = command.replace(option, "")
        output.path = command
    return RawStream(microphone=media.microphone, camera=media.camera)


@dataclass
class _RelaySource:
    headers: Dict[str, str]
    root_url: str
    proxies: list[str] = field(default_factory=list)
    proxy_index: int = 0
    playlist_logged: bool = False
    media_logged: bool = False

    @property
    def proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        return self.proxies[self.proxy_index % len(self.proxies)]

    def prefer(self, value: Optional[str]) -> None:
        if value and value in self.proxies:
            self.proxy_index = self.proxies.index(value)


class LiveHLSProxy:
    """Small token-scoped HLS reverse proxy bound only to loopback."""

    def __init__(self) -> None:
        self._sources: Dict[str, _RelaySource] = {}
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._port = 0
        self._proxy_lock = asyncio.Lock()
        self._proxy_cache: list[str] = []
        self._proxy_cache_until = 0.0

    async def register(self, url: str, headers: Dict[str, str]) -> tuple[str, str]:
        url = await _validate_public_url(url)
        await self._start()

        # Never report "started" merely because Telegram accepted the call.
        # First prove that the root manifest itself is readable HLS.
        proxies: list[str] = []
        if not await self._probe_manifest(url, headers, None):
            proxies = await self._find_working_proxies(url, headers)
            if not proxies:
                raise LiveResolveError(
                    "The live CDN is not reachable from this server right now"
                )
            log.info("Protected HLS manifest verified through a geo-compatible TLS tunnel")
        else:
            log.info("Protected HLS manifest verified directly from the hosting network")

        token = secrets.token_urlsafe(24)
        self._sources[token] = _RelaySource(dict(headers), url, proxies)
        return self._local_url(token, url), token

    def unregister(self, token: Optional[str]) -> None:
        if token:
            self._sources.pop(token, None)

    async def close(self) -> None:
        self._sources.clear()
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None
        self._port = 0

    async def _start(self) -> None:
        if self._runner is not None:
            return
        app = web.Application(client_max_size=_MAX_PLAYLIST)
        app.router.add_get("/{token}/{resource}", self._handle)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        server = getattr(site, "_server", None)
        sockets = server.sockets if server is not None else None
        if not sockets:
            await runner.cleanup()
            raise RuntimeError("Could not start the local HLS relay")
        self._port = int(sockets[0].getsockname()[1])
        timeout = aiohttp.ClientTimeout(total=None, connect=12, sock_connect=12, sock_read=45)
        self._session = aiohttp.ClientSession(timeout=timeout, auto_decompress=False)
        self._runner = runner
        self._site = site
        log.info("Local HLS relay listening on 127.0.0.1:%s", self._port)

    @staticmethod
    def _encode(url: str) -> str:
        return base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def _decode(value: str) -> str:
        if len(value) > 16_384:
            raise ValueError("Encoded URL is too long")
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding).decode("utf-8")

    @staticmethod
    def _is_public_proxy(value: str) -> bool:
        try:
            parsed = urllib.parse.urlsplit(value)
            ip = ipaddress.ip_address(parsed.hostname or "")
            port = parsed.port
        except (ValueError, TypeError):
            return False
        return bool(
            parsed.scheme == "http"
            and port
            and 0 < port < 65536
            and not (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            )
        )

    def _local_url(self, token: str, url: str) -> str:
        return f"http://127.0.0.1:{self._port}/{token}/{self._encode(url)}"

    async def _probe_manifest(
        self, url: str, headers: Dict[str, str], proxy: Optional[str]
    ) -> bool:
        if self._session is None:
            return False
        response: Optional[aiohttp.ClientResponse] = None
        try:
            response = await self._session.get(
                url,
                headers={**headers, "Accept-Encoding": "identity"},
                proxy=proxy,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=9),
            )
            if not 200 <= response.status < 300:
                return False
            body = await response.content.read(128 * 1024)
            content_type = response.headers.get("Content-Type", "").lower()
            return b"#EXTM3U" in body or "mpegurl" in content_type
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return False
        finally:
            if response is not None:
                response.release()

    async def _proxy_candidates(self) -> list[str]:
        if self._session is None:
            return []
        try:
            async with self._session.get(
                _PROXY_LIST_URL,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=12),
            ) as response:
                if response.status != 200:
                    return []
                text = (await response.content.read(256 * 1024)).decode("utf-8", "replace")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return []
        values = []
        for raw in text.splitlines():
            value = raw.strip()
            if value and self._is_public_proxy(value) and value not in values:
                values.append(value)
        return values[:_PROXY_PROBE_LIMIT]

    async def _find_working_proxies(
        self, url: str, headers: Dict[str, str], *, refresh: bool = False
    ) -> list[str]:
        async with self._proxy_lock:
            now = time.monotonic()
            cached = list(self._proxy_cache) if now < self._proxy_cache_until else []
            if cached and not refresh:
                good = []
                for proxy in cached:
                    if await self._probe_manifest(url, headers, proxy):
                        good.append(proxy)
                if good:
                    return good

            candidates = await self._proxy_candidates()
            # Recently successful exits go first, but only after a fresh probe.
            ordered = cached + [value for value in candidates if value not in cached]
            semaphore = asyncio.Semaphore(12)

            async def check(proxy: str) -> Optional[str]:
                async with semaphore:
                    return proxy if await self._probe_manifest(url, headers, proxy) else None

            tasks = [asyncio.create_task(check(proxy)) for proxy in ordered]
            working: list[str] = []
            try:
                for task in asyncio.as_completed(tasks):
                    value = await task
                    if value:
                        working.append(value)
                        if len(working) >= _PROXY_WANTED:
                            break
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            if working:
                self._proxy_cache = working
                self._proxy_cache_until = time.monotonic() + 180
            return working

    async def _request_once(
        self,
        url: str,
        headers: Dict[str, str],
        proxy: Optional[str],
    ) -> tuple[aiohttp.ClientResponse, str]:
        if self._session is None:
            raise RuntimeError("HLS relay is not running")
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            current = await _validate_public_url(current)
            response = await self._session.get(
                current,
                headers=headers,
                proxy=proxy,
                allow_redirects=False,
            )
            if response.status not in {301, 302, 303, 307, 308}:
                return response, current
            location = response.headers.get("Location")
            response.release()
            if not location:
                return response, current
            current = urllib.parse.urljoin(current, location)
        raise LiveResolveError("Too many redirects in the live stream")

    async def _request(
        self, url: str, headers: Dict[str, str], source: _RelaySource
    ) -> tuple[aiohttp.ClientResponse, str]:
        attempted: set[Optional[str]] = set()
        last_error: Optional[BaseException] = None

        async def try_values(values: list[Optional[str]]):
            nonlocal last_error
            for proxy in values:
                if proxy in attempted:
                    continue
                attempted.add(proxy)
                try:
                    response, final_url = await self._request_once(url, headers, proxy)
                except (aiohttp.ClientError, asyncio.TimeoutError, LiveResolveError) as exc:
                    last_error = exc
                    continue
                if proxy and response.status in _BLOCKED_STATUSES:
                    response.release()
                    continue
                source.prefer(proxy)
                return response, final_url
            return None

        current_first = [] if source.proxy is None else [source.proxy]
        current_first += [value for value in source.proxies if value != source.proxy]
        if not current_first:
            current_first = [None]
        answer = await try_values(current_first)
        if answer is not None:
            return answer

        # A public exit may disappear during playback. Refresh the small pool
        # against the known-good root manifest and retry the failed resource.
        if source.proxies:
            refreshed = await self._find_working_proxies(
                source.root_url, source.headers, refresh=True
            )
            if refreshed:
                source.proxies = refreshed
                source.proxy_index = 0
                answer = await try_values(list(refreshed))
                if answer is not None:
                    return answer

        raise LiveResolveError(
            "Upstream HLS request failed"
            + (f": {type(last_error).__name__}" if last_error else "")
        )

    def _rewrite_playlist(self, text: str, base_url: str, token: str) -> str:
        output = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#"):
                upstream = urllib.parse.urljoin(base_url, line)
                raw_line = self._local_url(token, upstream)
            elif line.startswith("#") and "URI=\"" in raw_line:
                raw_line = _URI_ATTRIBUTE.sub(
                    lambda match: 'URI="'
                    + self._local_url(token, urllib.parse.urljoin(base_url, match.group(1)))
                    + '"',
                    raw_line,
                )
            output.append(raw_line)
        return "\n".join(output) + "\n"

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        token = request.match_info["token"]
        source = self._sources.get(token)
        if source is None:
            raise web.HTTPNotFound()
        try:
            upstream_url = self._decode(request.match_info["resource"])
            await _validate_public_url(upstream_url)
        except (ValueError, UnicodeError, LiveResolveError):
            raise web.HTTPBadRequest() from None

        headers = dict(source.headers)
        headers["Accept-Encoding"] = "identity"
        if request.headers.get("Range"):
            headers["Range"] = request.headers["Range"]

        response: Optional[aiohttp.ClientResponse] = None
        relay: Optional[web.StreamResponse] = None
        try:
            response, final_url = await self._request(upstream_url, headers, source)
            content_type = response.headers.get("Content-Type", "")
            is_playlist = (
                "mpegurl" in content_type.lower()
                or urllib.parse.urlsplit(final_url).path.lower().endswith(".m3u8")
            )
            if is_playlist and response.status < 400:
                body = await response.content.read(_MAX_PLAYLIST + 1)
                if len(body) > _MAX_PLAYLIST:
                    raise web.HTTPBadGateway(text="HLS playlist is too large")
                text = body.decode(response.charset or "utf-8", "replace")
                if "#EXTM3U" not in text:
                    raise web.HTTPBadGateway(text="Upstream returned a non-HLS response")
                if not source.playlist_logged:
                    source.playlist_logged = True
                    log.info("FFmpeg opened the verified HLS playlist through the loopback relay")
                rewritten = self._rewrite_playlist(text, final_url, token)
                return web.Response(
                    text=rewritten,
                    status=response.status,
                    content_type="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": "no-store"},
                )

            outgoing = {}
            for name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                if response.headers.get(name):
                    outgoing[name] = response.headers[name]
            relay = web.StreamResponse(status=response.status, headers=outgoing)
            await relay.prepare(request)
            sent = 0
            async for chunk in response.content.iter_chunked(128 * 1024):
                sent += len(chunk)
                await relay.write(chunk)
                if sent >= 64 * 1024 and not source.media_logged:
                    source.media_logged = True
                    log.info("HLS media payload verified and flowing into FFmpeg")
            await relay.write_eof()
            return relay
        except (aiohttp.ClientError, asyncio.TimeoutError, LiveResolveError) as exc:
            log.warning("HLS relay request failed: %s", exc)
            raise web.HTTPBadGateway(text="Upstream HLS request failed") from None
        except ConnectionResetError:
            # FFmpeg may close one rendition as soon as it selects another.
            return relay if relay is not None else web.Response(status=499)
        finally:
            if response is not None:
                response.release()


# One relay is shared by every assistant/call instance in the process.
live_hls_proxy = LiveHLSProxy()
