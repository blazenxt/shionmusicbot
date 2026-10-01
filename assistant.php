<?php
/** Read-only assistant status. Session provisioning lives on a one-time page. */
declare(strict_types=1);
require_once __DIR__ . '/inc/ui.php';

header('Cache-Control: no-store');
header('X-Robots-Tag: noindex, nofollow');

$runtime = sh_runtime_dir();
$token = sh_env('BOT_TOKEN');
$bot = sh_env('BOT_USERNAME', 'ShionMusicBot');
$assistant = sh_env('ASSISTANT_USERNAME', 'ShionVCAssistant');
$assistant_id = sh_env('ASSISTANT_ID');
$session_configured = strlen(sh_env('SESSION_STRING', sh_env('SESSION1'))) > 40;
$login_required = is_file($runtime . '/SESSION_REQUIRED');
$provisioning_closed = is_file($runtime . '/auth/assistant-login.closed');
$st = sh_web_status();
$assistant_ready = is_array($st) && !empty($st['assistant_ready'])
    && time() - (int) ($st['ts'] ?? 0) < 90;

$me = null;
$bot_api_label = 'unreachable';
if ($token !== '') {
    $resp = sh_http_get('https://api.telegram.org/bot' . rawurlencode($token) . '/getMe', 10);
    $data = json_decode($resp['body'], true);
    $me = is_array($data) && !empty($data['ok']) ? ($data['result'] ?? null) : null;
    if ($me !== null) {
        $bot_api_label = 'online';
    } elseif (is_array($data) && (int) ($data['error_code'] ?? 0) === 429) {
        $bot_api_label = 'rate limited';
    } elseif (is_array($data) && (int) ($data['error_code'] ?? 0) === 401) {
        $bot_api_label = 'token rejected';
    }
}

$session_ok = $session_configured && !$login_required;
$session_label = $assistant_ready ? 'connected'
    : ($login_required ? 'login required' : ($session_configured ? 'saved / starting' : 'not configured'));

sh_header('assistant', 'Assistant Status', 'Read-only assistant and voice-engine health. Login uses a separate one-time page.');
?>

<section class="grid g3 mb">
  <div class="card">
    <h3><?php echo sh_icon('bot', 16); ?> Bot account</h3>
    <div class="kv"><span class="k">Username</span><span class="mono">@<?php echo sh_h((string) ($me['username'] ?? $bot)); ?></span></div>
    <div class="kv"><span class="k">ID</span><span class="mono"><?php echo sh_h((string) ($me['id'] ?? '—')); ?></span></div>
    <div class="kv"><span class="k">Bot API</span><?php echo sh_badge($me !== null, $bot_api_label); ?></div>
  </div>
  <div class="card">
    <h3><?php echo sh_icon('headphones', 16); ?> Assistant account</h3>
    <div class="kv"><span class="k">Username</span><span class="mono">@<?php echo sh_h($assistant); ?></span></div>
    <div class="kv"><span class="k">ID</span><span class="mono"><?php echo sh_h($assistant_id !== '' ? $assistant_id : '—'); ?></span></div>
    <div class="kv"><span class="k">Session</span><?php echo sh_badge($session_ok, $session_label); ?></div>
  </div>
  <div class="card">
    <h3><?php echo sh_icon('pulse', 16); ?> Voice engine</h3>
    <div class="kv"><span class="k">Current state</span><?php echo sh_badge($assistant_ready, $assistant_ready ? 'ready' : ($login_required ? 'login required' : 'starting')); ?></div>
    <div class="kv"><span class="k">Storage</span><span>Private server runtime</span></div>
    <div class="kv"><span class="k">Provisioning page</span><span><?php echo $provisioning_closed ? '404 / closed' : 'one-time'; ?></span></div>
  </div>
</section>

<?php if (!$provisioning_closed && !$assistant_ready) { ?>
<section class="card mb">
  <h3><?php echo sh_icon('shield', 16); ?> One-time session provisioning</h3>
  <p class="muted">Phone, OTP and 2FA are handled on a separate secure page. After a successful session save, that page permanently returns HTTP 404.</p>
  <a class="btn btn-primary" href="assistant-login.php">Open one-time login page</a>
</section>
<?php } ?>

<section class="card">
  <h3><?php echo sh_icon('settings', 16); ?> After connection</h3>
  <ol class="steps">
    <li>Add <b>@<?php echo sh_h($assistant); ?></b> to the Telegram group.</li>
    <li>Promote it with permission to manage voice chats.</li>
    <li>Start a voice chat, then send <code>/play song name</code> to <b>@<?php echo sh_h($bot); ?></b>.</li>
  </ol>
</section>

<?php sh_footer(); ?>
