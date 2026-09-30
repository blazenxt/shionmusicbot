#!/usr/bin/env python3
from __future__ import annotations

from shionmusicbot.config import get_config


def main() -> None:
    config = get_config()
    config.validate_runtime()
    print("Environment looks valid.")
    print(f"Bot name: {config.bot_name}")
    print(f"DB path: {config.database_path}")


if __name__ == "__main__":
    main()
