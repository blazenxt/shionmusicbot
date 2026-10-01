<?php
/** Secure assistant login/session manager. */
declare(strict_types=1);
require_once __DIR__ . '/inc/ui.php';

if (session_status() !== PHP_SESSION_ACTIVE) {
    session_set_cookie_params(array(
        'lifetime' => 0,
        'path' => dirname($_SERVER['SCRIPT_NAME']) . '/',
        'secure' => !empty($_SERVER['HTTPS']),
        'httponly' => true,
        'samesite' => 'Strict',
    ));
    session_start();
}
header('Cache-Control: no-store');
header('X-Robots-Tag: noindex, nofollow');

if (empty($_SESSION['csrf'])) {
    $_SESSION['csrf'] = bin2hex(random_bytes(24));
}
if (!empty($_SESSION['manager_at']) && time() - (int) $_SESSION['manager_at'] > 1200) {
    unset($_SESSION['manager_ok'], $_SESSION['manager_at'], $_SESSION['auth_step']);
}

function sh_csrf_ok(): bool
{
    return isset($_POST['csrf'], $_SESSION['csrf'])
        && hash_equals((string) $_SESSION['csrf'], (string) $_POST['csrf']);
}

function sh_auth_helper(array $payload): array
{
    if (!function_exists('proc_open')) {
        return array('ok' => false, 'error' => 'Server has proc_open disabled. Ask the host to enable it for this site.');
    }
    $runtime = sh_runtime_dir();
    $cmd = 'export SHION_RUNTIME_DIR=' . escapeshellarg($runtime)
        . '; exec ' . escapeshellarg(sh_python()) . ' ' . escapeshellarg(__DIR__ . '/session_auth.py');
    $pipes = array();
    $process = @proc_open(
        $cmd,
        array(0 => array('pipe', 'r'), 1 => array('pipe', 'w'), 2 => array('pipe', 'w')),
        $pipes,
        __DIR__
    );
    if (!is_resource($process)) {
        return array('ok' => false, 'error' => 'Could not start the private Telegram login helper.');
    }
    fwrite($pipes[0], json_encode($payload));
    fclose($pipes[0]);
    $stdout = stream_get_contents($pipes[1]);
    fclose($pipes[1]);
    stream_get_contents($pipes[2]); // deliberately do not expose traces/secrets
    fclose($pipes[2]);
    $code = proc_close($process);
    $lines = array_values(array_filter(array_map('trim', explode("\n", (string) $stdout))));
    $data = $lines ? json_decode((string) end($lines), true) : null;
    if (!is_array($data)) {
        return array('ok' => false, 'error' => 'Login helper did not return a valid response (exit ' . $code . ').');
    }
    return $data;
}

$message = '';
$message_ok = false;
$manager_key = sh_env('SESSION_MANAGER_KEY');

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!sh_csrf_ok()) {
        $message = 'Security check failed. Refresh the page and try again.';
    } else {
        $action = isset($_POST['action']) ? (string) $_POST['action'] : '';
        if ($action === 'unlock') {
            $given = (string) ($_POST['manager_key'] ?? '');
            if ($manager_key !== '' && hash_equals($manager_key, $given)) {
                session_regenerate_id(true);
                $_SESSION['manager_ok'] = true;
                $_SESSION['manager_at'] = time();
                $message = 'Assistant Manager unlocked for 20 minutes.';
                $message_ok = true;
            } else {
                usleep(600000);
                $message = 'Invalid manager key.';
            }
        } elseif ($action === 'logout') {
            unset($_SESSION['manager_ok'], $_SESSION['manager_at'], $_SESSION['auth_step']);
            $message = 'Manager locked.';
            $message_ok = true;
        } elseif (!empty($_SESSION['manager_ok'])) {
            $_SESSION['manager_at'] = time();
            set_time_limit(120);
            if ($action === 'send') {
                $result = sh_auth_helper(array('action' => 'send', 'phone' => (string) ($_POST['phone'] ?? '')));
            } elseif ($action === 'resend') {
                $result = sh_auth_helper(array('action' => 'resend'));
            } elseif ($action === 'verify') {
                $result = sh_auth_helper(array('action' => 'verify', 'code' => (string) ($_POST['code'] ?? '')));
            } elseif ($action === 'password') {
                $result = sh_auth_helper(array('action' => 'password', 'password' => (string) ($_POST['password'] ?? '')));
            } elseif ($action === 'reset') {
                $result = sh_auth_helper(array('action' => 'reset'));
            } else {
                $result = array('ok' => false, 'error' => 'Unknown action.');
            }
            $message_ok = !empty($result['ok']);
            $message = $message_ok
                ? (($result['step'] ?? '') === 'saved'
                    ? 'Assistant login successful. Session saved privately and bot restarted.'
                    : (($result['step'] ?? '') === 'password'
                        ? 'Code accepted. Enter the Telegram two-step verification password.'
                        : (($result['step'] ?? '') === 'code'
                            ? 'Telegram sent the login code. Enter it below.'
                            : 'Login flow reset.')))
                : (string) ($result['error'] ?? 'Telegram login failed.');
            if ($message_ok) {
                $_SESSION['auth_step'] = (string) ($result['step'] ?? 'phone');
                if (($result['step'] ?? '') === 'saved') {
                    sh_restart_bot();
                }
            }
        }
    }
}

$unlocked = !empty($_SESSION['manager_ok']);
$step = (string) ($_SESSION['auth_step'] ?? 'phone');
if ($unlocked) {
    $pending_file = sh_runtime_dir() . '/auth/pending.json';
    $pending = is_readable($pending_file)
        ? json_decode((string) file_get_contents($pending_file), true)
        : null;
    $pending_valid = is_array($pending)
        && in_array($pending['step'] ?? '', array('code', 'password'), true)
        && time() - (int) ($pending['created_at'] ?? 0) <= 900;
    if ($pending_valid) {
        $step = (string) $pending['step'];
        $_SESSION['auth_step'] = $step;
    } elseif (in_array($step, array('code', 'password'), true)) {
        // Do not leave the browser on a verification form after a reset or an
        // expired/missing server-side login request.
        $step = 'phone';
        $_SESSION['auth_step'] = 'phone';
    }
}

$token = sh_env('BOT_TOKEN');
$bot = sh_env('BOT_USERNAME', 'ShionMusicBot');
$assistant = sh_env('ASSISTANT_USERNAME', 'ShionVCAssistant');
$assistant_id = sh_env('ASSISTANT_ID');
$session_configured = strlen(sh_env('SESSION_STRING', sh_env('SESSION1'))) > 40;
$login_required = is_file(sh_runtime_dir() . '/SESSION_REQUIRED');
$st = sh_web_status();
$assistant_ready = is_array($st) && !empty($st['assistant_ready']) && time() - (int) ($st['ts'] ?? 0) < 90;

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
$session_label = $login_required ? 'needs replacement' : ($session_configured ? 'yes' : 'no');

sh_header('assistant', 'Assistant Manager', 'Secure Telegram login, private session storage and automatic bot restart.');
?>

<?php if ($message !== '') { ?>
<div class="notice <?php echo $message_ok ? 'notice-ok' : 'notice-bad'; ?> mb"><?php echo sh_h($message); ?></div>
<?php } ?>

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
    <div class="kv"><span class="k">Security</span><span>Codes and passwords are never logged</span></div>
  </div>
</section>

<section class="card mb auth-card">
  <div class="row spread">
    <div>
      <h3><?php echo sh_icon('shield', 16); ?> Secure session setup</h3>
      <p class="muted">Use the assistant account's phone number. Telegram sends the code in the Telegram app; SMS is only used when Telegram chooses it.</p>
    </div>
    <?php if ($unlocked) { ?>
    <form method="post" class="inline-form">
      <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['csrf']); ?>">
      <input type="hidden" name="action" value="logout">
      <button class="btn btn-ghost" type="submit">Lock manager</button>
    </form>
    <?php } ?>
  </div>

  <?php if (!$unlocked) { ?>
  <form method="post" autocomplete="off" class="auth-form">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['csrf']); ?>">
    <input type="hidden" name="action" value="unlock">
    <label for="manager_key">Manager key</label>
    <div class="form-row">
      <input id="manager_key" name="manager_key" type="password" required autocomplete="current-password" placeholder="Private dashboard key">
      <button class="btn btn-primary" type="submit">Unlock</button>
    </div>
  </form>
  <?php } elseif ($step === 'code') { ?>
  <form method="post" autocomplete="one-time-code" class="auth-form">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['csrf']); ?>">
    <input type="hidden" name="action" value="verify">
    <label for="code">Telegram login code</label>
    <div class="form-row">
      <input id="code" name="code" inputmode="numeric" pattern="[0-9 ]{4,12}" required placeholder="12345">
      <button class="btn btn-primary" type="submit">Verify code</button>
    </div>
    <p class="muted">Use the newest code from Telegram. Requesting another code immediately invalidates every older code.</p>
  </form>
  <?php } elseif ($step === 'password') { ?>
  <form method="post" autocomplete="off" class="auth-form">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['csrf']); ?>">
    <input type="hidden" name="action" value="password">
    <label for="password">Telegram two-step verification password</label>
    <div class="form-row">
      <input id="password" name="password" type="password" required autocomplete="current-password" placeholder="2FA password">
      <button class="btn btn-primary" type="submit">Finish login</button>
    </div>
  </form>
  <?php } elseif ($step === 'saved') { ?>
  <div class="notice notice-ok">Session is saved. The voice assistant is restarting; Live Status should turn ready shortly.</div>
  <?php } else { ?>
  <form method="post" autocomplete="off" class="auth-form">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['csrf']); ?>">
    <input type="hidden" name="action" value="send">
    <label for="phone">Assistant phone number</label>
    <div class="form-row">
      <input id="phone" name="phone" type="tel" required autocomplete="tel" placeholder="+919876543210">
      <button class="btn btn-primary" type="submit">Send login code</button>
    </div>
  </form>
  <?php } ?>

  <?php if ($unlocked && $step === 'code') { ?>
  <form method="post" class="inline-form mt">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['csrf']); ?>">
    <input type="hidden" name="action" value="resend">
    <button class="btn btn-primary" type="submit">Send a new code</button>
  </form>
  <?php } ?>

  <?php if ($unlocked && in_array($step, array('code', 'password', 'saved'), true)) { ?>
  <form method="post" class="inline-form mt">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['csrf']); ?>">
    <input type="hidden" name="action" value="reset">
    <button class="btn btn-ghost" type="submit">Start again</button>
  </form>
  <?php } ?>
</section>

<section class="card">
  <h3><?php echo sh_icon('settings', 16); ?> After login</h3>
  <ol class="steps">
    <li>Add <b>@<?php echo sh_h($assistant); ?></b> to the Telegram group.</li>
    <li>Promote it with permission to manage voice chats.</li>
    <li>Start a voice chat, then send <code>/play song name</code> to <b>@<?php echo sh_h($bot); ?></b>.</li>
  </ol>
</section>

<?php sh_footer(); ?>
