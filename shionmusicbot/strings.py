from __future__ import annotations

START_TEXT = """
<b>🎧 Shion Music bot</b>

Main Telegram group voice chats me high quality music stream kar sakta hoon.
Assistant account ko group me add karo, voice chat start karo,
fir <code>/play song name</code> use karo.

<b>Maintainer:</b> @blazenxt
""".strip()

HELP_TEXT = """
<b>🎧 Shion Music bot commands</b>

<b>Music</b>
• <code>/play song name</code> — YouTube/search se play
• <code>/play YouTube/link</code> — URL play
• <code>/play</code> — replied audio/video play
• <code>/playlist playlist-link</code> — playlist queue
• <code>/radio stream-url</code> — live radio/direct stream
• <code>/queue</code> — queue dekho
• <code>/now</code> — current song

<b>Controls</b>
• <code>/pause</code>, <code>/resume</code>
• <code>/skip</code> or <code>/skip 3</code>
• <code>/stop</code> / <code>/end</code>
• <code>/seek 1:20</code>
• <code>/volume 1-200</code>
• <code>/loop off|one|queue</code>
• <code>/shuffle</code>
• <code>/join</code>, <code>/leave</code>

<b>Admin / DJ</b>
• <code>/auth</code> reply to user — DJ permission
• <code>/unauth</code> reply to user
• <code>/authusers</code>
• <code>/dj on|off</code> — restrict /play to admins/auth users
• <code>/settings</code>

<b>Notes</b>
Bot account commands handle karta hai.
Assistant user account voice chat join karke audio stream karta hai.
""".strip()

ABOUT_TEXT = """
<b>Shion Music bot</b>
Open-source Telegram VC music bot made for @blazenxt.

Tech: Python, Pyrogram, PyTgCalls, yt-dlp, FFmpeg.
""".strip()

NEED_GROUP = "Ye command group me use karo."
NEED_ADMIN = "Is command ke liye admin ya authorized DJ hona zaroori hai."
NEED_QUERY = (
    "Song name, link, ya replied audio/video do. Example: <code>/play faded alan walker</code>"
)
SEARCHING = "🔎 Searching / preparing track..."
NO_QUEUE = "Queue empty hai."
NOTHING_PLAYING = "Abhi kuch play nahi ho raha."
VC_JOIN_HINT = "Voice chat start karo aur assistant account ko group me add/admin karo."
