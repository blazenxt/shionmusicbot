<?php
/** One-time, key-gated assistant session provisioning page. */
declare(strict_types=1);
require_once __DIR__ . '/inc/ui.php';

$runtime = sh_runtime_dir();
$closed_file = $runtime . '/auth/assistant-login.closed';

function sh_login_not_found(): void
{
    http_response_code(404);
    header('Cache-Control: no-store');
    header('X-Robots-Tag: noindex, nofollow');
    header('Content-Type: text/html; charset=utf-8');
    echo '<!doctype html><html><head><meta charset="utf-8"><title>404 Not Found</title></head>'
        . '<body><h1>404 Not Found</h1><p>The requested page was not found.</p></body></html>';
    exit;
}

// This endpoint permanently disappears after the first successful login.
if (is_file($closed_file)) {
    sh_login_not_found();
}

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

if (empty($_SESSION['assistant_login_csrf'])) {
    $_SESSION['assistant_login_csrf'] = bin2hex(random_bytes(24));
}
if (!empty($_SESSION['assistant_manager_at']) && time() - (int) $_SESSION['assistant_manager_at'] > 1200) {
    unset($_SESSION['assistant_manager_ok'], $_SESSION['assistant_manager_at'], $_SESSION['assistant_auth_step']);
}

function sh_login_csrf_ok(): bool
{
    return isset($_POST['csrf'], $_SESSION['assistant_login_csrf'])
        && hash_equals((string) $_SESSION['assistant_login_csrf'], (string) $_POST['csrf']);
}

function sh_login_helper(array $payload): array
{
    if (!function_exists('proc_open')) {
        return array('ok' => false, 'error' => 'Server login helper is unavailable.');
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
    stream_get_contents($pipes[2]);
    fclose($pipes[2]);
    $code = proc_close($process);
    $lines = array_values(array_filter(array_map('trim', explode("\n", (string) $stdout))));
    $data = $lines ? json_decode((string) end($lines), true) : null;
    return is_array($data)
        ? $data
        : array('ok' => false, 'error' => 'Login helper returned an invalid response (exit ' . $code . ').');
}

function sh_close_login_page(string $closed_file): void
{
    @mkdir(dirname($closed_file), 0700, true);
    $tmp = $closed_file . '.tmp';
    file_put_contents($tmp, json_encode(array('closed_at' => time())));
    @chmod($tmp, 0600);
    rename($tmp, $closed_file);
}

$message = '';
$message_ok = false;
$manager_key = sh_env('SESSION_MANAGER_KEY');

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (!sh_login_csrf_ok()) {
        $message = 'Security check failed. Refresh the page and try again.';
    } else {
        $action = (string) ($_POST['action'] ?? '');
        if ($action === 'begin') {
            $given = (string) ($_POST['manager_key'] ?? '');
            if ($manager_key !== '' && hash_equals($manager_key, $given)) {
                session_regenerate_id(true);
                $_SESSION['assistant_manager_ok'] = true;
                $_SESSION['assistant_manager_at'] = time();
                set_time_limit(120);
                $result = sh_login_helper(array(
                    'action' => 'send',
                    'phone' => (string) ($_POST['phone'] ?? ''),
                ));
                $message_ok = !empty($result['ok']);
                $result_step = (string) ($result['step'] ?? '');
                $message = $message_ok
                    ? ($result_step === 'saved'
                        ? 'Session saved.'
                        : 'Telegram sent a login code. Enter the newest code below.')
                    : (string) ($result['error'] ?? 'Telegram login failed.');
                if ($message_ok) {
                    $_SESSION['assistant_auth_step'] = $result_step !== '' ? $result_step : 'phone';
                    if ($result_step === 'saved') {
                        sh_close_login_page($closed_file);
                        sh_restart_bot();
                        unset($_SESSION['assistant_manager_ok'], $_SESSION['assistant_auth_step']);
                        header('Location: ' . basename(__FILE__), true, 303);
                        exit;
                    }
                }
            } else {
                usleep(600000);
                $message = 'Invalid manager key.';
            }
        } elseif ($action === 'logout') {
            unset($_SESSION['assistant_manager_ok'], $_SESSION['assistant_manager_at'], $_SESSION['assistant_auth_step']);
            $message = 'Login page locked.';
            $message_ok = true;
        } elseif (!empty($_SESSION['assistant_manager_ok'])) {
            $_SESSION['assistant_manager_at'] = time();
            set_time_limit(120);
            if ($action === 'send') {
                $result = sh_login_helper(array('action' => 'send', 'phone' => (string) ($_POST['phone'] ?? '')));
            } elseif ($action === 'resend') {
                $result = sh_login_helper(array('action' => 'resend'));
            } elseif ($action === 'verify') {
                $result = sh_login_helper(array('action' => 'verify', 'code' => (string) ($_POST['code'] ?? '')));
            } elseif ($action === 'password') {
                $result = sh_login_helper(array('action' => 'password', 'password' => (string) ($_POST['password'] ?? '')));
            } elseif ($action === 'reset') {
                $result = sh_login_helper(array('action' => 'reset'));
            } else {
                $result = array('ok' => false, 'error' => 'Unknown action.');
            }

            $message_ok = !empty($result['ok']);
            $result_step = (string) ($result['step'] ?? '');
            $message = $message_ok
                ? ($result_step === 'password'
                    ? 'Code accepted. Enter the Telegram two-step verification password.'
                    : ($result_step === 'code'
                        ? 'Telegram sent a fresh login code. Enter the newest code below.'
                        : ($result_step === 'phone' ? 'Login flow reset.' : 'Session saved.')))
                : (string) ($result['error'] ?? 'Telegram login failed.');

            if ($message_ok) {
                $_SESSION['assistant_auth_step'] = $result_step !== '' ? $result_step : 'phone';
                if ($result_step === 'saved') {
                    sh_close_login_page($closed_file);
                    sh_restart_bot();
                    unset($_SESSION['assistant_manager_ok'], $_SESSION['assistant_auth_step']);
                    // Redirect to the same URL; the closed-file gate now returns 404.
                    header('Location: ' . basename(__FILE__), true, 303);
                    exit;
                }
            }
        }
    }
}

$unlocked = !empty($_SESSION['assistant_manager_ok']);
$step = (string) ($_SESSION['assistant_auth_step'] ?? 'phone');
if ($unlocked) {
    $pending_file = $runtime . '/auth/pending.json';
    $pending = is_readable($pending_file)
        ? json_decode((string) file_get_contents($pending_file), true)
        : null;
    $pending_valid = is_array($pending)
        && in_array($pending['step'] ?? '', array('code', 'password'), true)
        && time() - (int) ($pending['created_at'] ?? 0) <= 900;
    if ($pending_valid) {
        $step = (string) $pending['step'];
        $_SESSION['assistant_auth_step'] = $step;
    } elseif (in_array($step, array('code', 'password'), true)) {
        $step = 'phone';
        $_SESSION['assistant_auth_step'] = 'phone';
    }
}

sh_header('assistant', 'One-time Assistant Login', 'This secure page permanently becomes 404 after the session is saved.');
?>

<?php if ($message !== '') { ?>
<div class="notice <?php echo $message_ok ? 'notice-ok' : 'notice-bad'; ?> mb"><?php echo sh_h($message); ?></div>
<?php } ?>

<section class="card mb auth-card">
  <div class="row spread">
    <div>
      <h3><?php echo sh_icon('shield', 16); ?> Secure Telegram session setup</h3>
      <p class="muted">Codes and passwords are sent only to the private helper and are never logged. After success this URL returns HTTP 404.</p>
    </div>
    <?php if ($unlocked) { ?>
    <form method="post" class="inline-form">
      <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['assistant_login_csrf']); ?>">
      <input type="hidden" name="action" value="logout">
      <button class="btn btn-ghost" type="submit">Lock</button>
    </form>
    <?php } ?>
  </div>

  <ol class="steps mb">
    <li>Enter the private manager key and assistant phone number.</li>
    <li>Enter the newest code received inside Telegram.</li>
    <li>Enter 2FA only when Telegram requests it.</li>
  </ol>

  <?php if (!$unlocked) { ?>
  <form method="post" autocomplete="off" class="auth-form">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['assistant_login_csrf']); ?>">
    <input type="hidden" name="action" value="begin">
    <label for="manager_key">Manager key</label>
    <div class="form-row mb">
      <input id="manager_key" name="manager_key" type="password" required autocomplete="current-password" placeholder="Private dashboard key">
    </div>
    <label for="phone">Assistant phone number</label>
    <div class="form-row">
      <input id="phone" name="phone" type="tel" inputmode="tel" required autocomplete="tel" placeholder="+919876543210">
      <button class="btn btn-primary" type="submit">Send Telegram code</button>
    </div>
  </form>
  <?php } elseif ($step === 'code') { ?>
  <form method="post" autocomplete="one-time-code" class="auth-form">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['assistant_login_csrf']); ?>">
    <input type="hidden" name="action" value="verify">
    <label for="code">Newest Telegram login code</label>
    <div class="form-row">
      <input id="code" name="code" inputmode="numeric" pattern="[0-9 ]{4,12}" required placeholder="12345">
      <button class="btn btn-primary" type="submit">Verify code</button>
    </div>
  </form>
  <form method="post" class="inline-form mt">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['assistant_login_csrf']); ?>">
    <input type="hidden" name="action" value="resend">
    <button class="btn btn-ghost" type="submit">Send another code</button>
  </form>
  <?php } elseif ($step === 'password') { ?>
  <form method="post" autocomplete="off" class="auth-form">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['assistant_login_csrf']); ?>">
    <input type="hidden" name="action" value="password">
    <label for="password">Telegram two-step verification password</label>
    <div class="form-row">
      <input id="password" name="password" type="password" required autocomplete="current-password" placeholder="2FA password">
      <button class="btn btn-primary" type="submit">Save session</button>
    </div>
  </form>
  <?php } else { ?>
  <form method="post" autocomplete="off" class="auth-form">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['assistant_login_csrf']); ?>">
    <input type="hidden" name="action" value="send">
    <label for="phone">Assistant phone number</label>
    <div class="form-row">
      <input id="phone" name="phone" type="tel" required autocomplete="tel" placeholder="+919876543210">
      <button class="btn btn-primary" type="submit">Send login code</button>
    </div>
  </form>
  <?php } ?>

  <?php if ($unlocked && in_array($step, array('code', 'password'), true)) { ?>
  <form method="post" class="inline-form mt">
    <input type="hidden" name="csrf" value="<?php echo sh_h((string) $_SESSION['assistant_login_csrf']); ?>">
    <input type="hidden" name="action" value="reset">
    <button class="btn btn-ghost" type="submit">Start again</button>
  </form>
  <?php } ?>
</section>

<?php sh_footer(); ?>
