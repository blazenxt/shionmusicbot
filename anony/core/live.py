"""Safe live-page/HLS resolver for ``/live`` and ``/vlive``."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, Optional

import aiohttp

_MAX_BODY = 2_000_000
_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
)


class LiveResolveError(Exception):
    pass


@dataclass
class LiveSource:
    url: str
    title: str = "Live stream"
    headers: Dict[str, str] = field(default_factory=dict)


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _validate_public_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise LiveResolveError("Invalid URL") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise LiveResolveError("Only public HTTP/HTTPS links are supported")
    if parsed.username or parsed.password:
        raise LiveResolveError("URLs containing credentials are not supported")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise LiveResolveError("Private hosts are not allowed")
    try:
        answers = await asyncio.get_running_loop().getaddrinfo(
            host, parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise LiveResolveError("Could not resolve the stream host") from exc
    if not answers or any(not _is_public_ip(item[4][0]) for item in answers):
        raise LiveResolveError("Private or unsafe stream hosts are not allowed")
    return urllib.parse.urlunsplit(parsed)


async def _fetch_text(session: aiohttp.ClientSession, url: str, referer: str = "") -> tuple[str, str, str]:
    url = await _validate_public_url(url)
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/vnd.apple.mpegurl,*/*"}
    if referer:
        headers["Referer"] = referer
    try:
        async with session.get(url, headers=headers, allow_redirects=True) as response:
            response.raise_for_status()
            final_url = await _validate_public_url(str(response.url))
            raw = await response.content.read(_MAX_BODY + 1)
            if len(raw) > _MAX_BODY:
                raise LiveResolveError("Live page is too large")
            return raw.decode(response.charset or "utf-8", "replace"), final_url, response.headers.get("Content-Type", "")
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise LiveResolveError("Could not fetch the live page") from exc


def _parse_m3u(text: str, wanted_id: str) -> Optional[LiveSource]:
    current: Optional[dict] = None
    headers: Dict[str, str] = {}
    wanted = wanted_id.strip().lower()
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            attrs = {k.lower(): v for k, v in re.findall(r'([\w-]+)="([^"]*)"', line)}
            name = line.rsplit(",", 1)[-1].strip() if "," in line else "Live stream"
            current = {"id": attrs.get("tvg-id", ""), "name": name}
            headers = {}
        elif current is not None and line.startswith("#EXTVLCOPT:http-user-agent="):
            headers["User-Agent"] = line.split("=", 1)[1]
        elif current is not None and line.startswith("#EXTVLCOPT:http-referrer="):
            headers["Referer"] = line.split("=", 1)[1]
        elif current is not None and line.startswith("#EXTVLCOPT:http-cookie="):
            headers["Cookie"] = line.split("=", 1)[1]
        elif current is not None and line.startswith("#EXTHTTP:"):
            try:
                extra = json.loads(line.split(":", 1)[1])
                if isinstance(extra, dict):
                    for key, value in extra.items():
                        clean = "Referer" if key.lower() in {"referrer", "referer"} else str(key)
                        headers[clean] = str(value)
            except (ValueError, TypeError):
                pass
        elif current is not None and re.match(r"^https?://", line, re.I):
            current_id = str(current.get("id", "")).lower()
            current_name = str(current.get("name", ""))
            if not wanted or wanted in {current_id, current_name.lower()}:
                return LiveSource(line, current_name or "Live stream", dict(headers))
            current = None
            headers = {}
    return None


async def resolve_live_url(page_url: str) -> LiveSource:
    """Resolve direct HLS links and player pages (including Plugx SLIV)."""
    timeout = aiohttp.ClientTimeout(total=35, connect=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        clean_url = await _validate_public_url(page_url.strip())
        parsed = urllib.parse.urlsplit(clean_url)
        if parsed.path.lower().endswith(".m3u8"):
            return LiveSource(clean_url, parsed.hostname or "Live stream", {"User-Agent": _USER_AGENT})

        html, final_url, content_type = await _fetch_text(session, clean_url)
        if "mpegurl" in content_type.lower() or html.lstrip().startswith("#EXTM3U"):
            return LiveSource(final_url, parsed.hostname or "Live stream", {"User-Agent": _USER_AGENT})

        query = urllib.parse.parse_qs(urllib.parse.urlsplit(final_url).query)
        wanted_id = (query.get("id") or [""])[0]
        playlist_match = re.search(r"PLAYLIST_URL\s*=\s*['\"]([^'\"]+)['\"]", html, re.I)
        if playlist_match and wanted_id:
            playlist_url = urllib.parse.urljoin(final_url, playlist_match.group(1))
            playlist, _, _ = await _fetch_text(session, playlist_url, final_url)
            source = _parse_m3u(playlist, wanted_id)
            if source is not None:
                source.url = await _validate_public_url(source.url)
                source.headers.setdefault("User-Agent", _USER_AGENT)
                source.headers.setdefault("Referer", final_url)
                return source

        # Generic HTML players often expose a direct m3u8 in file/src/source.
        candidates = re.findall(r"https?://[^\"'<>\\\s]+\.m3u8[^\"'<>\\\s]*", html, re.I)
        for candidate in candidates:
            candidate = candidate.replace("\\/", "/").replace("&amp;", "&")
            try:
                candidate = await _validate_public_url(candidate)
            except LiveResolveError:
                continue
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
            title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else "Live stream"
            return LiveSource(candidate, title or "Live stream", {"User-Agent": _USER_AGENT, "Referer": final_url})

    raise LiveResolveError("No playable HLS stream was found on this page")
