"""Loopback HLS relay used for protected live streams.

Some CDNs require browser headers and can make the bundled static FFmpeg TLS
client unstable.  FFmpeg therefore reads a loopback HLS URL while this relay
fetches the public playlists/segments with aiohttp, applies the required
headers, and rewrites every nested HLS URI back through the relay.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Dict, Optional

import aiohttp
from aiohttp import web

from anony.core.live import LiveResolveError, _validate_public_url

log = logging.getLogger(__name__)

_MAX_PLAYLIST = 2_000_000
_MAX_REDIRECTS = 5
_URI_ATTRIBUTE = re.compile(r'URI="([^"]+)"')


@dataclass(frozen=True)
class _RelaySource:
    headers: Dict[str, str]


class LiveHLSProxy:
    """Small token-scoped HLS reverse proxy bound only to loopback."""

    def __init__(self) -> None:
        self._sources: Dict[str, _RelaySource] = {}
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._port = 0

    async def register(self, url: str, headers: Dict[str, str]) -> tuple[str, str]:
        url = await _validate_public_url(url)
        await self._start()
        token = secrets.token_urlsafe(24)
        self._sources[token] = _RelaySource(dict(headers))
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
        sockets = getattr(site, "_server", None).sockets
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

    def _local_url(self, token: str, url: str) -> str:
        return f"http://127.0.0.1:{self._port}/{token}/{self._encode(url)}"

    async def _request(
        self, url: str, headers: Dict[str, str]
    ) -> tuple[aiohttp.ClientResponse, str]:
        if self._session is None:
            raise RuntimeError("HLS relay is not running")
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            current = await _validate_public_url(current)
            response = await self._session.get(current, headers=headers, allow_redirects=False)
            if response.status not in {301, 302, 303, 307, 308}:
                return response, current
            location = response.headers.get("Location")
            response.release()
            if not location:
                return response, current
            current = urllib.parse.urljoin(current, location)
        raise LiveResolveError("Too many redirects in the live stream")

    def _rewrite_playlist(self, text: str, base_url: str, token: str) -> str:
        output = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#"):
                upstream = urllib.parse.urljoin(base_url, line)
                raw_line = self._local_url(token, upstream)
            elif line.startswith("#") and "URI=\"" in raw_line:
                raw_line = _URI_ATTRIBUTE.sub(
                    lambda match: 'URI="' + self._local_url(
                        token, urllib.parse.urljoin(base_url, match.group(1))
                    ) + '"',
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
        try:
            response, final_url = await self._request(upstream_url, headers)
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
            async for chunk in response.content.iter_chunked(128 * 1024):
                await relay.write(chunk)
            await relay.write_eof()
            return relay
        except (aiohttp.ClientError, asyncio.TimeoutError, LiveResolveError) as exc:
            log.warning("HLS relay request failed: %s", exc)
            raise web.HTTPBadGateway(text="Upstream HLS request failed") from None
        except ConnectionResetError:
            # FFmpeg may close one rendition as soon as it selects another.
            return web.Response(status=499)
        finally:
            if response is not None:
                response.release()


# One relay is shared by every assistant/call instance in the process.
live_hls_proxy = LiveHLSProxy()
