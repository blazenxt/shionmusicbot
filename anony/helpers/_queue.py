"""In-memory per-chat queue manager."""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from anony.helpers._dataclass import Track


class Queue:
    """Thread-safe, per-chat FIFO track queue with a "now playing" slot."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._queues: Dict[int, List[Track]] = {}
        self._now: Dict[int, Optional[Track]] = {}

    # ── current track ──────────────────────────────────────────────
    def getnow(self, chat_id: int) -> Optional[Track]:
        with self._lock:
            return self._now.get(chat_id)

    def setnow(self, chat_id: int, track: Optional[Track]) -> None:
        with self._lock:
            self._now[int(chat_id)] = track

    # ── queue operations ───────────────────────────────────────────
    def put(self, chat_id: int, track: Track) -> int:
        """Append a track; returns its 1-based position in the queue."""
        with self._lock:
            bucket = self._queues.setdefault(int(chat_id), [])
            bucket.append(track)
            return len(bucket)

    def force_add(self, chat_id: int, track: Track) -> None:
        """Insert a track at the front of the queue (next up)."""
        with self._lock:
            self._queues.setdefault(int(chat_id), []).insert(0, track)

    def get(self, chat_id: int) -> List[Track]:
        with self._lock:
            return list(self._queues.get(int(chat_id), []))

    def pop(self, chat_id: int) -> Optional[Track]:
        with self._lock:
            bucket = self._queues.get(int(chat_id))
            if not bucket:
                return None
            return bucket.pop(0)

    def remove(self, chat_id: int, position: int) -> Optional[Track]:
        """Remove a queued track by its 1-based position."""
        with self._lock:
            bucket = self._queues.get(int(chat_id))
            if not bucket or not 1 <= position <= len(bucket):
                return None
            return bucket.pop(position - 1)

    def clear(self, chat_id: int) -> int:
        """Drop the whole queue (not the playing track); returns removed count."""
        with self._lock:
            bucket = self._queues.pop(int(chat_id), [])
            return len(bucket)

    def replace(self, chat_id: int, items: list) -> None:
        """Swap the whole queue content (used by /shuffle)."""
        with self._lock:
            self._queues[int(chat_id)] = list(items)

    def clear_all(self, chat_id: int) -> int:
        """Drop queue *and* the playing slot."""
        removed = self.clear(chat_id)
        with self._lock:
            self._now.pop(int(chat_id), None)
        return removed

    def size(self, chat_id: int) -> int:
        with self._lock:
            return len(self._queues.get(int(chat_id), []))

    def all(self) -> Dict[int, List[Track]]:
        with self._lock:
            return {cid: list(items) for cid, items in self._queues.items()}


#: Shared queue singleton.
queue = Queue()
