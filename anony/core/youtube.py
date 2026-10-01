"""Testweb3 YouTube proxy engine — the single source for search & streams.

**Single Stream Policy:** every YouTube search, metadata fetch and media
stream resolution goes exclusively through the Testweb3 proxy
(``config.YT_API_BASE`` → ``http://Testweb3.cstsc.in/yt/``).  There is no
yt-dlp CLI usage and no direct scraping of googlevideo endpoints, which
keeps the hosting IP clean and avoids rate limits entirely.

Endpoints used
--------------
* ``GET api.php?action=search&q={query}``
  → ``{"ok": true, "data": {"videos": [ … ]}}``
* ``GET api.php?action=video&id={video_id}``
  → ``{"ok": true, "data": {"title", "duration", "thumbnail",
     "recovery_stream": {"url": "stream.php?t=…"}}}``

The ``recovery_stream.url`` token is short lived, so the player refreshes
video info right before piping the stream into PyTgCalls.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional

import aiohttp

from config import config

log = logging.getLogger(__name__)

_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/)|youtu\.be/)"
    r"([0-9A-Za-z_-]{11})"
)


def video_id_from_url(text: str) -> Optional[str]:
    """Extract an 11-char video id from any YouTube URL form."""
    if not text:
        return None
    match = _VIDEO_ID_RE.search(text)
    return match.group(1) if match else None


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def duration_text(seconds: int) -> str:
    """Render seconds as ``h:mm:ss`` / ``m:ss``."""
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def seconds_from_text(text: str) -> int:
    """Parse ``h:mm:ss`` / ``mm:ss`` / ``ss`` into seconds."""
    if not text:
        return 0
    parts = str(text).strip().split(":")
    if not all(p.strip().isdigit() for p in parts if p != ""):
        return 0
    try:
        values = [int(p or 0) for p in parts]
    except ValueError:
        return 0
    seconds = 0
    for value in values:
        seconds = seconds * 60 + value
    return seconds


class YouTubeError(Exception):
    """Raised when the Testweb3 proxy cannot be reached or misbehaves."""


class YouTubeEngine:
    """Async client for the Testweb3 proxy with caching and retries."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        cache_ttl: int = 300,
        timeout: int = 30,
    ) -> None:
        self.base = (base_url or config.YT_API_BASE or "").rstrip("/") + "/"
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = cache_ttl
        self._session: Optional[aiohttp.ClientSession] = None
        self._timeout = aiohttp.ClientTimeout(total=timeout, connect=10)

    # ── HTTP plumbing ──────────────────────────────────────────────
    async def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                headers={
                    "User-Agent": "ShionMusicBot/1.0 "
                    "(Telegram music bot; Testweb3 proxy client)",
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _get_json(self, params: Dict[str, str]) -> Dict[str, Any]:
        url = self.base + "api.php?" + urllib.parse.urlencode(params)
        session = await self.session()
        last_error: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = await response.json(content_type=None)
                if not isinstance(data, dict):
                    raise YouTubeError("unexpected payload from Testweb3")
                return data
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                ValueError,
                YouTubeError,
            ) as exc:
                last_error = exc
                if attempt == 1:
                    await asyncio.sleep(1.5)
        raise YouTubeError(f"Testweb3 request failed: {last_error}")

    # ── normalisation ──────────────────────────────────────────────
    @staticmethod
    def _normalize_search(item: Dict[str, Any]) -> Dict[str, Any]:
        duration = _to_int(item.get("duration"))
        return {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or "Unknown"),
            "duration": duration,
            "duration_text": str(item.get("duration_text") or duration_text(duration)),
            "views_text": str(item.get("views_text") or ""),
            "thumbnail": str(item.get("thumbnail") or ""),
            "channel": str(item.get("channel") or ""),
            "is_live": bool(item.get("is_live")),
        }

    def _normalize_video(self, video_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        duration = _to_int(data.get("duration"))
        recovery = data.get("recovery_stream") or {}
        if not isinstance(recovery, dict):
            recovery = {}
        raw_url = recovery.get("url") or ""
        stream_url = urllib.parse.urljoin(self.base, raw_url) if raw_url else None
        views = data.get("views")
        views_text = data.get("views_text") or (
            f"{int(views):,} views" if isinstance(views, int) else ""
        )
        return {
            "id": str(data.get("id") or video_id),
            "title": str(data.get("title") or "Unknown"),
            "duration": duration,
            "duration_text": str(data.get("duration_text") or duration_text(duration)),
            "thumbnail": str(data.get("thumbnail") or ""),
            "channel": str(data.get("channel") or ""),
            "views_text": str(views_text),
            "stream_url": stream_url,
            "is_live": bool(data.get("is_live")),
        }

    # ── public API ─────────────────────────────────────────────────
    async def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search YouTube through Testweb3; returns normalised results."""
        try:
            payload = await self._get_json({"action": "search", "q": query})
        except YouTubeError as exc:
            log.warning("Search failed for %r: %s", query, exc)
            return []
        if not payload.get("ok"):
            log.warning("Search rejected for %r: %s", query, payload.get("error"))
            return []
        videos = (payload.get("data") or {}).get("videos") or []
        results: List[Dict[str, Any]] = []
        for item in videos:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            entry = self._normalize_search(item)
            if entry["is_live"]:
                continue  # live streams are unreliable playback sources
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    async def video(
        self, video_id: str, *, refresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Fetch video metadata + stream URL (cached for ``cache_ttl``)."""
        now = time.monotonic()
        if not refresh:
            cached = self._cache.get(video_id)
            if cached and now - cached[0] < self._cache_ttl:
                return cached[1]
        try:
            payload = await self._get_json({"action": "video", "id": video_id})
        except YouTubeError as exc:
            log.warning("Video fetch failed for %s: %s", video_id, exc)
            return None
        if not payload.get("ok"):
            return None
        info = self._normalize_video(video_id, payload.get("data") or {})
        self._cache[video_id] = (now, info)
        if len(self._cache) > 512:  # simple FIFO trim
            self._cache.pop(next(iter(self._cache)))
        return info

    async def refresh_stream(self, video_id: str) -> Optional[Dict[str, Any]]:
        """Force a fresh fetch — stream tokens are short lived."""
        return await self.video(video_id, refresh=True)


#: Shared engine instance used across the bot.
youtube = YouTubeEngine()
