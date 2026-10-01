#!/usr/bin/env python3
"""Remove unapproved ShionMusicBot cron jobs through the CyberPanel UI API.

Configuration is read from the private runtime ``panel_guard.json``. Nothing
sensitive is accepted on argv or written to stdout.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any


def post_json(opener, url: str, data: dict[str, Any], csrf: str, referer: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={
            "Content-Type": "application/json",
            "X-CSRFToken": csrf,
            "Referer": referer,
            "User-Agent": "ShionMusicBot-CronGuard/1.0",
        },
        method="POST",
    )
    with opener.open(request, timeout=20) as response:
        value = json.loads(response.read().decode("utf-8", "replace"))
        return value if isinstance(value, dict) else {}


def main() -> int:
    runtime_raw = os.environ.get("SHION_RUNTIME_DIR", "").strip()
    if not runtime_raw:
        return 2
    runtime = Path(runtime_raw).expanduser()
    path = runtime / "panel_guard.json"
    if not path.is_file():
        return 0
    try:
        path.chmod(0o600)
        cfg = json.loads(path.read_text(encoding="utf-8"))
        panel = str(cfg["panel_url"]).rstrip("/")
        username = str(cfg["username"])
        password = str(cfg["password"])
        domain = str(cfg["domain"])
        project = str(cfg["project"])
        approved = str(cfg["approved_command"])
    except (OSError, KeyError, TypeError, ValueError):
        return 2

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "ShionMusicBot-CronGuard/1.0")]
    try:
        with opener.open(panel + "/", timeout=20):
            pass
        csrf = next((c.value for c in jar if c.name == "csrftoken"), "")
        login = post_json(
            opener,
            panel + "/verifyLogin",
            {"username": username, "password": password, "languageSelection": "english", "twofa": None},
            csrf,
            panel + "/",
        )
        if login.get("loginStatus") != 1:
            return 3
        csrf = next((c.value for c in jar if c.name == "csrftoken"), csrf)
        referer = panel + "/websites/" + domain + "/manageCron"
        result = post_json(opener, panel + "/websites/getWebsiteCron", {"domain": domain}, csrf, referer)
        crons = result.get("crons") if isinstance(result.get("crons"), list) else []
        bad = []
        for item in crons:
            command = str(item.get("command", ""))
            if command == approved:
                continue
            command_lower = command.lower()
            if (
                project.lower() in command_lower
                or str(runtime).lower() in command_lower
                or "shionmusicbot" in command_lower
                or "shion_alive" in command_lower
            ):
                try:
                    bad.append(int(item["line"]))
                except (KeyError, TypeError, ValueError):
                    pass
        removed = 0
        for line in sorted(set(bad), reverse=True):
            answer = post_json(
                opener,
                panel + "/websites/remCronbyLine",
                {"domain": domain, "line": line},
                csrf,
                referer,
            )
            if answer.get("remCronbyLine") == 1:
                removed += 1
        if removed:
            print(f"removed {removed} unapproved panel cron entr{'y' if removed == 1 else 'ies'}")
        return 0
    except Exception as exc:
        print(f"panel guard error: {type(exc).__name__}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
