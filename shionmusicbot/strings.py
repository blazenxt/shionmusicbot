from __future__ import annotations

START_TEXT = """
<b>🎧 Shion Music bot</b>

I stream high-quality music in Telegram group voice chats.
Add the assistant account to your group, start a voice chat, and use
<code>/play song name</code> to begin.

<b>Maintainer:</b> @zucms
""".strip()

HELP_TEXT = """
<b>🎧 Shion Music bot commands</b>

<b>Music</b>
• <code>/play song name</code> — play from YouTube/search
• <code>/play YouTube/link</code> — play a URL
• <code>/play</code> — play replied audio/video
• <code>/vplay song name</code> — play video in VC screen-share/presentation mode
• <code>/playlist playlist-link</code> — queue a playlist
• <code>/radio stream-url</code> — play a live radio/direct stream
• <code>/queue</code> — show the queue
• <code>/now</code> — show the current track

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
• <code>/auth</code> reply to user — grant DJ permission
• <code>/unauth</code> reply to user
• <code>/authusers</code>
• <code>/dj on|off</code> — restrict /play to admins/auth users
• <code>/settings</code>

<b>Notes</b>
The bot account handles commands.
The assistant user account joins the voice chat and streams audio.
""".strip()

ABOUT_TEXT = """
<b>Shion Music bot</b>
Open-source Telegram VC music bot maintained by @zucms.

Tech: Python, Pyrogram, PyTgCalls, yt-dlp, FFmpeg.
""".strip()

NEED_GROUP = "Use this command in a group."
NEED_ADMIN = "This command requires an admin or an authorized DJ."
NEED_QUERY = (
    "Send a song name, link, or replied audio/video. Example: <code>/play faded alan walker</code>"
)
SEARCHING = "🔎 Searching / preparing track..."
NO_QUEUE = "The queue is empty."
NOTHING_PLAYING = "Nothing is playing right now."
VC_JOIN_HINT = "Start a voice chat and add/promote the assistant account in the group."
