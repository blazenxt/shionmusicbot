from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

from .models import Track
from .utils import is_url, truncate

logger = logging.getLogger(__name__)

YOUTUBE_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be")
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
PREMIUMTUBE_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


class DownloadError(RuntimeError):
    pass


class Downloader:
    def __init__(
        self,
        downloads_dir: Path,
        *,
        max_duration_seconds: int,
        max_file_size_mb: int,
        playlist_limit: int,
        cookie_file: str | None = None,
        yt_api_base: str | None = None,
    ) -> None:
        self.downloads_dir = downloads_dir
        self.max_duration_seconds = max_duration_seconds
        self.max_file_size_mb = max_file_size_mb
        self.playlist_limit = playlist_limit
        self.cookie_file = cookie_file
        self.yt_api_base = yt_api_base.rstrip("/") if yt_api_base else None

    async def resolve(self, query: str, requester_id: int, requester_name: str) -> Track:
        query = query.strip()
        if not query:
            raise DownloadError("Empty query")

        external = await self._resolve_with_external_api(query, requester_id, requester_name)
        if external:
            return external

        return await asyncio.to_thread(
            self._resolve_with_ytdlp, query, requester_id, requester_name
        )

    async def resolve_playlist(
        self, query: str, requester_id: int, requester_name: str
    ) -> list[Track]:
        query = query.strip()
        if not query:
            raise DownloadError("Empty playlist query")
        return await asyncio.to_thread(
            self._resolve_playlist_with_ytdlp, query, requester_id, requester_name
        )

    async def from_telegram_reply(
        self, reply: Any, requester_id: int, requester_name: str
    ) -> Track:
        media = (
            getattr(reply, "audio", None)
            or getattr(reply, "voice", None)
            or getattr(reply, "video", None)
            or getattr(reply, "document", None)
        )
        if media is None:
            raise DownloadError("Reply to an audio, voice, video, or document message.")

        file_size = getattr(media, "file_size", None)
        if file_size and file_size > self.max_file_size_mb * 1024 * 1024:
            raise DownloadError(f"File too large. Max {self.max_file_size_mb} MB allowed.")

        chat_dir = self.downloads_dir / str(reply.chat.id)
        chat_dir.mkdir(parents=True, exist_ok=True)
        path = await reply.download(file_name=str(chat_dir) + "/")
        if not path:
            raise DownloadError("Telegram media download failed.")

        title = (
            getattr(media, "title", None)
            or getattr(media, "file_name", None)
            or getattr(reply, "caption", None)
            or "Telegram audio"
        )
        duration = getattr(media, "duration", None)
        return Track(
            title=truncate(str(title), 100),
            source=str(path),
            requester_id=requester_id,
            requester_name=requester_name,
            duration=int(duration) if duration else None,
            webpage_url=None,
            cleanup_path=Path(path),
            is_live=False,
        )

    async def _resolve_with_external_api(
        self, query: str, requester_id: int, requester_name: str
    ) -> Track | None:
        """Resolve through an optional self-hosted YouTube/PremiumTube endpoint.

        Supported formats:
        1. Generic JSON endpoint: {base}?q=<query> returning url/stream_url/audio_url.
        2. PremiumTube-style endpoint: {base}/api.php?action=search|video.
        """
        if not self.yt_api_base:
            return None
        try:
            premium = await self._resolve_with_premiumtube(query, requester_id, requester_name)
            if premium:
                return premium
        except DownloadError:
            raise
        except Exception as exc:  # pragma: no cover - optional network hook
            logger.debug("PremiumTube API failed: %s", exc)

        try:
            import aiohttp

            url = f"{self.yt_api_base}?q={quote_plus(query)}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as response:
                    if response.status >= 400:
                        return None
                    data = await response.json(content_type=None)
        except Exception as exc:  # pragma: no cover - optional network hook
            logger.debug("External YT API failed: %s", exc)
            return None

        if isinstance(data, list) and data:
            data = data[0]
        if isinstance(data, dict):
            payload = data.get("result") or data.get("data") or data
            if isinstance(payload, list) and payload:
                payload = payload[0]
            if not isinstance(payload, dict):
                return None
            source = self._payload_source(payload)
            if not source:
                return None
            return Track(
                title=str(payload.get("title") or query),
                source=urljoin(self.yt_api_base + "/", str(source)),
                requester_id=requester_id,
                requester_name=requester_name,
                duration=_safe_int(payload.get("duration")),
                webpage_url=str(payload.get("webpage_url") or payload.get("url") or source),
                thumbnail=payload.get("thumbnail"),
                is_live=bool(payload.get("is_live", False)),
            )
        return None

    async def _resolve_with_premiumtube(
        self, query: str, requester_id: int, requester_name: str
    ) -> Track | None:
        import aiohttp

        base = self.yt_api_base or ""
        api_base = base if base.endswith("/") else base + "/"
        api_url = urljoin(api_base, "api.php")
        video_id = self._extract_youtube_id(query)
        headers = {**PREMIUMTUBE_HEADERS, "Referer": api_base}
        timeout = aiohttp.ClientTimeout(total=60, sock_connect=15, sock_read=30)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            if not video_id:
                async with session.get(
                    api_url,
                    params={"action": "search", "q": query, "region": "India"},
                ) as response:
                    if response.status >= 400:
                        return None
                    search_data = await response.json(content_type=None)
                videos = (search_data.get("data") or {}).get("videos") or []
                if not videos:
                    return None
                video_id = videos[0].get("id")
                if not video_id:
                    return None

            async with session.get(
                api_url,
                params={"action": "video", "id": video_id, "region": "India"},
            ) as response:
                if response.status >= 400:
                    return None
                detail_data = await response.json(content_type=None)

            payload = detail_data.get("data") or {}
            if not isinstance(payload, dict):
                return None
            source = self._payload_source(payload)
            if not source:
                return None
            source_url = urljoin(api_base, str(source))
            duration = _safe_int(payload.get("duration"))
            is_live_track = bool(payload.get("is_live", False))
            if duration and duration > self.max_duration_seconds and not is_live_track:
                max_minutes = self.max_duration_seconds // 60
                raise DownloadError(
                    f"Track too long: {duration // 60} min. Max {max_minutes} min allowed."
                )

            # Premium Tube stream.php links are long proxy URLs. PyTgCalls/FFmpeg can
            # hang on some hosts when reading those URLs directly. Mature VC bots first
            # prepare a local playable file; doing the same here keeps playback stable.
            local_source = source_url
            cleanup_path: Path | None = None
            if not is_live_track and source_url.startswith("http"):
                cleanup_path = await self._download_remote_media(
                    session,
                    source_url,
                    video_id=video_id,
                    referer=api_base,
                )
                local_source = str(cleanup_path)

        webpage_url = urljoin(api_base, f"?v={video_id}")
        return Track(
            title=str(payload.get("title") or query),
            source=local_source,
            requester_id=requester_id,
            requester_name=requester_name,
            duration=duration,
            webpage_url=webpage_url,
            thumbnail=payload.get("thumbnail"),
            cleanup_path=cleanup_path,
            is_live=is_live_track,
        )

    async def _download_remote_media(
        self,
        session: Any,
        source_url: str,
        *,
        video_id: str,
        referer: str,
    ) -> Path:
        cache_dir = self.downloads_dir / "premiumtube"
        cache_dir.mkdir(parents=True, exist_ok=True)
        final_path = cache_dir / f"{video_id}-{uuid.uuid4().hex[:8]}.mp4"
        temp_path = final_path.with_suffix(".part")
        max_bytes = self.max_file_size_mb * 1024 * 1024
        headers = {"Referer": referer, "User-Agent": PREMIUMTUBE_HEADERS["User-Agent"]}
        written = 0
        try:
            async with session.get(source_url, headers=headers) as response:
                if response.status >= 400:
                    raise DownloadError(f"Premium Tube stream returned HTTP {response.status}")
                content_length = _safe_int(response.headers.get("Content-Length"))
                if content_length and content_length > max_bytes:
                    raise DownloadError(f"File too large. Max {self.max_file_size_mb} MB allowed.")
                with temp_path.open("wb") as fp:
                    async for chunk in response.content.iter_chunked(256 * 1024):
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > max_bytes:
                            raise DownloadError(
                                f"File too large. Max {self.max_file_size_mb} MB allowed."
                            )
                        fp.write(chunk)
            if written == 0:
                raise DownloadError("Premium Tube stream download returned an empty file.")
            temp_path.replace(final_path)
            logger.info("Prepared Premium Tube media file %s (%s bytes)", final_path, written)
            return final_path
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    @staticmethod
    def _payload_source(payload: dict[str, Any]) -> str | None:
        direct = (
            payload.get("stream_url")
            or payload.get("audio_url")
            or payload.get("url")
            or payload.get("link")
        )
        if direct:
            return str(direct)
        recovery = payload.get("recovery_stream")
        if isinstance(recovery, dict) and recovery.get("url"):
            return str(recovery["url"])
        qualities = payload.get("qualities")
        if isinstance(qualities, list):
            for quality in qualities:
                if (
                    isinstance(quality, dict)
                    and quality.get("type") == "progressive"
                    and quality.get("url")
                ):
                    return str(quality["url"])
            for quality in qualities:
                if isinstance(quality, dict) and quality.get("url"):
                    return str(quality["url"])
        return payload.get("webpage_url")

    @staticmethod
    def _extract_youtube_id(query: str) -> str | None:
        query = query.strip()
        if YOUTUBE_ID_RE.fullmatch(query):
            return query
        if not is_url(query):
            return None
        parsed = urlparse(query)
        host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
        if host == "youtu.be":
            candidate = parsed.path.strip("/").split("/", 1)[0]
            return candidate if YOUTUBE_ID_RE.fullmatch(candidate) else None
        if "youtube.com" in host:
            if parsed.path.startswith("/watch"):
                candidate = parse_qs(parsed.query).get("v", [""])[0]
                return candidate if YOUTUBE_ID_RE.fullmatch(candidate) else None
            for prefix in ("/shorts/", "/live/", "/embed/"):
                if parsed.path.startswith(prefix):
                    candidate = parsed.path.removeprefix(prefix).split("/", 1)[0]
                    return candidate if YOUTUBE_ID_RE.fullmatch(candidate) else None
        return None

    def _base_ytdlp_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "nocheckcertificate": True,
            "format": "bestaudio/best",
            "source_address": "0.0.0.0",
        }
        if self.cookie_file:
            options["cookiefile"] = self.cookie_file
        return options

    def _resolve_with_ytdlp(self, query: str, requester_id: int, requester_name: str) -> Track:
        import yt_dlp

        options = self._base_ytdlp_options()
        options["noplaylist"] = True
        lookup = query if is_url(query) else f"ytsearch1:{query}"

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(lookup, download=False)
        except Exception as exc:
            if is_url(query):
                logger.info("yt-dlp failed for direct URL, trying raw stream: %s", exc)
                return Track(
                    title=query.rsplit("/", 1)[-1] or query,
                    source=query,
                    requester_id=requester_id,
                    requester_name=requester_name,
                    webpage_url=query,
                    is_live=True,
                )
            raise DownloadError(f"Track resolve failed: {exc}") from exc

        if not info:
            raise DownloadError("No result found.")
        if info.get("_type") in {"playlist", "multi_video"}:
            entries = [entry for entry in info.get("entries", []) if entry]
            if not entries:
                raise DownloadError("No playable result found.")
            info = entries[0]

        return self._track_from_info(info, query, requester_id, requester_name)

    def _resolve_playlist_with_ytdlp(
        self, query: str, requester_id: int, requester_name: str
    ) -> list[Track]:
        import yt_dlp

        options = self._base_ytdlp_options()
        options.update({"extract_flat": "in_playlist", "playlistend": self.playlist_limit})
        lookup = query if is_url(query) else f"ytsearch{self.playlist_limit}:{query}"

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(lookup, download=False)
        except Exception as exc:
            raise DownloadError(f"Playlist resolve failed: {exc}") from exc

        tracks: list[Track] = []
        if not info:
            return tracks
        if info.get("_type") in {"playlist", "multi_video"}:
            entries = [entry for entry in info.get("entries", []) if entry]
            for entry in entries[: self.playlist_limit]:
                try:
                    tracks.append(self._track_from_info(entry, query, requester_id, requester_name))
                except DownloadError:
                    continue
        else:
            tracks.append(self._track_from_info(info, query, requester_id, requester_name))
        return tracks

    def _track_from_info(
        self, info: dict[str, Any], original_query: str, requester_id: int, requester_name: str
    ) -> Track:
        title = str(info.get("title") or original_query)
        duration = _safe_int(info.get("duration"))
        is_live_track = bool(info.get("is_live") or info.get("live_status") == "is_live")
        if duration and duration > self.max_duration_seconds and not is_live_track:
            max_minutes = self.max_duration_seconds // 60
            raise DownloadError(
                f"Track too long: {duration // 60} min. Max {max_minutes} min allowed."
            )

        webpage_url = info.get("webpage_url") or info.get("original_url") or info.get("url")
        source = self._best_source(info, webpage_url)
        if not source:
            raise DownloadError("Playable source not found.")

        return Track(
            title=title,
            source=source,
            requester_id=requester_id,
            requester_name=requester_name,
            duration=duration,
            webpage_url=webpage_url,
            thumbnail=info.get("thumbnail"),
            is_live=is_live_track,
        )

    @staticmethod
    def _best_source(info: dict[str, Any], webpage_url: str | None) -> str | None:
        extractor = str(info.get("extractor_key") or info.get("ie_key") or "").lower()
        raw_url = info.get("url")
        video_id = info.get("id")

        # PyTgCalls has built-in yt-dlp handling for YouTube links, so keep YouTube
        # as a webpage URL. This prevents expiring direct media URLs in long queues.
        if "youtube" in extractor:
            if webpage_url:
                return str(webpage_url)
            if video_id:
                return f"https://www.youtube.com/watch?v={video_id}"

        if webpage_url and any(host in str(webpage_url).lower() for host in YOUTUBE_HOSTS):
            return str(webpage_url)
        if raw_url:
            raw = str(raw_url)
            if raw.startswith("http"):
                return raw
            if "youtube" in extractor:
                return f"https://www.youtube.com/watch?v={raw}"
        if webpage_url:
            return str(webpage_url)
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None
