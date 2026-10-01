"""Thumbnail fetching / caching for 'now playing' replies."""

from __future__ import annotations

import logging
from typing import Optional

from anony.core.dir import CACHE
from anony.helpers._dataclass import Media

log = logging.getLogger(__name__)


async def fetch_thumbnail(media: Media) -> Optional[str]:
    """Download (and cache) the thumbnail of ``media``.

    Returns a local path usable by ``reply_photo`` or ``None`` — never
    raises; thumbnails are decorative.
    """
    if not media.thumbnail:
        return None
    try:
        path = CACHE / f"{media.video_id or 'thumb'}.jpg"
        if path.exists() and path.stat().st_size > 512:
            return str(path)

        from anony.core.youtube import youtube

        session = await youtube.session()
        async with session.get(media.thumbnail) as response:
            response.raise_for_status()
            data = await response.read()
        if not data:
            return None
        CACHE.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        return str(path)
    except Exception as exc:  # noqa: BLE001
        log.debug("Thumbnail fetch failed for %s: %s", media.video_id, exc)
        return None
