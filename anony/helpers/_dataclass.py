"""Media / track dataclasses."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Media:
    """Normalised YouTube media description (Testweb3 sourced)."""

    video_id: str
    title: str
    duration: int = 0
    duration_text: str = "0:00"
    thumbnail: str = ""
    views_text: str = ""
    channel: str = ""
    stream_url: Optional[str] = None
    is_live: bool = False

    @classmethod
    def from_search(cls, entry: dict) -> "Media":
        return cls(
            video_id=str(entry.get("id") or ""),
            title=str(entry.get("title") or "Unknown"),
            duration=int(entry.get("duration") or 0),
            duration_text=str(entry.get("duration_text") or "0:00"),
            thumbnail=str(entry.get("thumbnail") or ""),
            views_text=str(entry.get("views_text") or ""),
            channel=str(entry.get("channel") or ""),
            is_live=bool(entry.get("is_live")),
        )

    @classmethod
    def from_info(cls, info: dict) -> "Media":
        return cls(
            video_id=str(info.get("id") or ""),
            title=str(info.get("title") or "Unknown"),
            duration=int(info.get("duration") or 0),
            duration_text=str(info.get("duration_text") or "0:00"),
            thumbnail=str(info.get("thumbnail") or ""),
            views_text=str(info.get("views_text") or ""),
            channel=str(info.get("channel") or ""),
            stream_url=info.get("stream_url"),
            is_live=bool(info.get("is_live")),
        )

    @property
    def link(self) -> str:
        return f"https://youtu.be/{self.video_id}" if self.video_id else ""


@dataclass
class Track:
    """A queued media item bound to a chat."""

    media: Media
    chat_id: int
    requester_id: Optional[int] = None
    requester_name: str = "Unknown"
    is_video: bool = False
    queued_at: float = field(default_factory=time.time)
    file_path: Optional[str] = None

    @property
    def title(self) -> str:
        return self.media.title

    @property
    def duration_text(self) -> str:
        return self.media.duration_text

    def summary(self) -> str:
        icon = "🎬" if self.is_video else "🎵"
        return f"{icon} [{self.duration_text}] **{self.title}** — {self.requester_name}"
