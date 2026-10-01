"""Dynamic evaluator used by the owner-only ``/exec`` debug command."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional


async def aexec(code: str, env: Optional[Dict[str, Any]] = None) -> Any:
    """Execute ``code`` with ``await`` support and return its result.

    The snippet runs inside an ``async def`` wrapper; ``return`` inside
    the snippet produces the return value.  Strictly owner-only — see
    ``anony/plugins/misc.py``.
    """
    source = "async def __aexec__():\n"
    for line in code.rstrip().splitlines():
        source += f"    {line}\n" if line.strip() else "\n"
    scope: Dict[str, Any] = dict(env or {})
    scope["asyncio"] = asyncio
    exec(compile(source, "<shion-exec>", "exec"), scope)  # noqa: S102 - owner tool
    return await scope["__aexec__"]()
