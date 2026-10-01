from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from uuid import uuid4

from .utils import format_duration, truncate


@dataclass(slots=True)
class Track:
    title: str
    source: str
    requester_id: int
    requester_name: str
    duration: int | None = None
    webpage_url: str | None = None
    thumbnail: str | None = None
    cleanup_path: Path | None = None
    headers: dict[str, str] = field(default_factory=dict)
    is_live: bool = False
    video: bool = False
    start_at: int = 0
    uid: str = ""

    def __post_init__(self) -> None:
        if not self.uid:
            self.uid = uuid4().hex[:10]

    @property
    def display_title(self) -> str:
        return truncate(self.title, 70)

    @property
    def display_duration(self) -> str:
        return "Live" if self.is_live else format_duration(self.duration)

    def line(self, index: int | None = None) -> str:
        prefix = f"{index}. " if index is not None else ""
        return f"{prefix}<b>{self.display_title}</b> — <code>{self.display_duration}</code>"

    def clone_for_replay(self) -> "Track":
        return replace(self, start_at=0, uid=uuid4().hex[:10])
