"""Importing this package registers all Pyrogram handlers."""

from . import basic as basic
from . import music as music

__all__ = ("basic", "music")
