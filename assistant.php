<?php
/**
 * ShionMusicBot — assistant manager page.
 * Verifies both accounts against the Telegram Bot API (server-side only,
 * the token is never rendered) and documents the setup flow.
 */

require_once __DIR__ . '/inc/ui.php';

$token = sh_env('BOT_TOKEN');
$bot = sh_env('BOT_USERNAME', 'ShionMusicBot');
$assistant = sh_env('ASSISTANT_USERNAME', 'ShionVCAssistant');
$assistant_id = sh_env('ASSISTANT_ID');

$me = null;
$api_ok = false;
if ($token !== '') {
    $resp = sh_http_get("https://api.telegram.org/bot{$token}/getMe", 10);
    $data = json_decode($resp['body'], true);
    $api_ok = is_array($data) && !empty($data['ok']);
    $me = $api_ok && isset($data['result']) ? $data['result'] : null;
}

sh_header('assistant', 'Assistant Manager', 'The bot + assistant duo that powers your voice chats.');
?>

<section class="grid g3 mb">
  <div class="card">
    <h3><?php echo sh_icon('bot', 16); ?> Bot account</h3>
    <?php if ($me !== null) { ?>
      <div class="kv"><span class="k">Username</span><span class="mono">@<?php echo sh_h((string) $me['username']); ?></span></div>
      <div class="kv"><span class="k">Name</span><span><?php echo sh_h((string) $me['first_name']); ?></span></div>
      <div class="kv"><span class="k">ID</span><span class="mono"><?php echo sh_h((string) $me['id']); ?></span></div>
      <div class="kv"><span class="k">API</span><?php echo sh_badge(true, 'online'); ?></div>
    <?php } elseif ($api_ok) { ?>
      <p class="muted">API reachable but <code>getMe</code> failed — token revoked?</p>
    <?php } else { ?>
      <p class="muted">Telegram API unreachable from this host right now.</p>
    <?php } ?>
  </div>

  <div class="card">
    <h3><?php echo sh_icon('headphones', 16); ?> Assistant account</h3>
    <div class="kv"><span class="k">Username</span><span class="mono">@<?php echo sh_h($assistant); ?></span></div>
    <div class="kv"><span class="k">ID</span><span class="mono"><?php echo sh_h($assistant_id !== '' ? $assistant_id : '—'); ?></span></div>
    <div class="kv"><span class="k">Role</span><span>Joins voice chats &amp; streams media</span></div>
    <div class="kv"><span class="k">Session</span><span>Pyrogram v2 string session</span></div>
  </div>

  <div class="card">
    <h3><?php echo sh_icon('shield', 16); ?> Recommended rights</h3>
    <div class="kv"><span class="k">Assistant</span><span>Promote to <b>admin</b> with “Manage voice chats”</span></div>
    <div class="kv"><span class="k">Bot</span><span>No admin rights required</span></div>
    <div class="kv"><span class="k">Invite links</span><span>Give the bot “Invite users” to auto-join the assistant</span></div>
  </div>
</section>

<section class="card mb">
  <h3><?php echo sh_icon('settings', 16); ?> Setup flow</h3>
  <table>
    <thead><tr><th>#</th><th>Step</th><th>Detail</th></tr></thead>
    <tbody>
      <tr><td>1</td><td>Add the bot</td><td>Open <a href="https://t.me/<?php echo sh_h($bot); ?>?startgroup=true" target="_blank" rel="noopener">@<?php echo sh_h($bot); ?></a> and add it to your group.</td></tr>
      <tr><td>2</td><td>Add the assistant</td><td>Add <b>@<?php echo sh_h($assistant); ?></b> as a member (or admin) of the same group.</td></tr>
      <tr><td>3</td><td>Start a voice chat</td><td>Any admin starts a voice / video chat in the group (Shion can also create it when the assistant is admin).</td></tr>
      <tr><td>4</td><td>Play</td><td>Send <code>/play despacito</code> — the assistant joins and starts streaming.</td></tr>
      <tr><td>5</td><td>Control</td><td>Use the inline buttons or <code>/skip</code>, <code>/seek 1:30</code>, <code>/loop 2</code>, <code>/stop</code>.</td></tr>
    </tbody>
  </table>
</section>

<section class="card">
  <h3><?php echo sh_icon('pulse', 16); ?> Troubleshooting</h3>
  <table>
    <tbody>
      <tr><td class="mono">"Assistant is not in this chat"</td><td>Add <b>@<?php echo sh_h($assistant); ?></b> to the group, or give the bot permission to export invite links so it can auto-join.</td></tr>
      <tr><td class="mono">No audio</td><td>Make sure a voice chat is actually running, then retry <code>/play</code>.</td></tr>
      <tr><td class="mono">Skips a track</td><td>The streaming token expired — the queue engine automatically moves to the next track.</td></tr>
      <tr><td class="mono">/vplay disabled</td><td>Video playback is disabled via <code>VIDEO_PLAY</code> in the configuration.</td></tr>
    </tbody>
  </table>
</section>

<?php sh_footer(); ?>
