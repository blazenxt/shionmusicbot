<?php
/** Shared process/runtime helpers for the ShionMusicBot dashboard. */
declare(strict_types=1);

function sh_runtime_dir(): string
{
    static $dir = null;
    if ($dir !== null) {
        return $dir;
    }
    $override = trim((string) getenv('SHION_RUNTIME_DIR'));
    if ($override !== '') {
        $dir = rtrim($override, '/');
        return $dir;
    }
    $home = dirname(__DIR__, 5);
    $private = $home . '/private/shionmusicbot_runtime';
    if (is_dir($home . '/private') || is_dir($private)) {
        $dir = $private;
    } else {
        $dir = __DIR__ . '/.runtime';
    }
    return $dir;
}

function sh_env_path(): string
{
    $private = sh_runtime_dir() . '/bot.env';
    return is_file($private) ? $private : __DIR__ . '/.env';
}

function sh_env(string $key, string $default = ''): string
{
    static $env = null;
    if ($env === null) {
        $env = array();
        $path = sh_env_path();
        if (is_readable($path)) {
            foreach ((array) file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
                $line = trim((string) $line);
                if ($line === '' || $line[0] === '#' || strpos($line, '=') === false) {
                    continue;
                }
                list($k, $v) = explode('=', $line, 2);
                $env[trim($k)] = trim($v);
            }
        }
    }
    return isset($env[$key]) && $env[$key] !== '' ? $env[$key] : $default;
}

function sh_key_ok(): bool
{
    $expected = sh_env('RUNNER_KEY');
    $given = isset($_SERVER['HTTP_X_RUNNER_KEY']) ? (string) $_SERVER['HTTP_X_RUNNER_KEY']
        : (isset($_GET['key']) ? (string) $_GET['key'] : '');
    return $expected !== '' && $given !== '' && hash_equals($expected, $given);
}

function sh_run(string $cmd): string
{
    $out = @shell_exec($cmd . ' 2>&1');
    return is_string($out) ? $out : '';
}

function sh_python(): string
{
    $path = sh_runtime_dir() . '/venv/bin/python3';
    return is_executable($path) ? $path : 'python3';
}

function sh_pid(): int
{
    $path = sh_runtime_dir() . '/bot.pid';
    if (!is_readable($path)) {
        return 0;
    }
    $raw = trim((string) file_get_contents($path));
    return ctype_digit($raw) ? (int) $raw : 0;
}

function sh_proc_running(): bool
{
    $pid = sh_pid();
    if ($pid < 2) {
        return false;
    }
    $alive = function_exists('posix_kill') ? @posix_kill($pid, 0)
        : trim(sh_run('kill -0 ' . $pid . ' 2>/dev/null; echo $?')) === '0';
    if (!$alive) {
        @unlink(sh_runtime_dir() . '/bot.pid');
        return false;
    }
    $cwd = @readlink('/proc/' . $pid . '/cwd');
    $project = realpath(__DIR__);
    return $cwd !== false && $project !== false && realpath($cwd) === $project;
}

function sh_stop_bot(): void
{
    $pid = sh_pid();
    if ($pid < 2 || !sh_proc_running()) {
        @unlink(sh_runtime_dir() . '/bot.pid');
        return;
    }
    if (function_exists('posix_kill')) {
        @posix_kill($pid, 15);
    } else {
        sh_run('kill ' . $pid);
    }
    for ($i = 0; $i < 40 && sh_proc_running(); $i++) {
        usleep(100000);
    }
    if (sh_proc_running()) {
        function_exists('posix_kill') ? @posix_kill($pid, 9) : sh_run('kill -9 ' . $pid);
    }
    @unlink(sh_runtime_dir() . '/bot.pid');
}

function sh_start_bot(): bool
{
    if (sh_proc_running()) {
        return true;
    }
    $runtime = sh_runtime_dir();
    @mkdir($runtime, 0700, true);
    @mkdir($runtime . '/data', 0700, true);
    $python = sh_python();
    $cmd = 'cd ' . escapeshellarg(__DIR__) . ' || exit 1; '
        . 'export SHION_RUNTIME_DIR=' . escapeshellarg($runtime) . '; '
        . 'export PATH=' . escapeshellarg($runtime . '/bin') . ':$PATH; '
        . 'nohup ' . escapeshellarg($python) . ' -m anony >> '
        . escapeshellarg($runtime . '/bot.log') . ' 2>&1 < /dev/null & '
        . 'echo $! > ' . escapeshellarg($runtime . '/bot.pid');
    // Redirect the launcher shell itself so PHP never keeps an inherited pipe
    // open for the lifetime of the background Python process.
    @shell_exec('bash -c ' . escapeshellarg($cmd) . ' >/dev/null 2>&1');
    usleep(800000);
    return sh_proc_running();
}

function sh_restart_bot(): bool
{
    sh_stop_bot();
    return sh_start_bot();
}

function sh_tail(string $file, int $lines = 80): array
{
    if (!is_readable($file)) {
        return array();
    }
    $all = file($file, FILE_IGNORE_NEW_LINES);
    return $all === false ? array() : array_slice($all, -$lines);
}

function sh_web_status(): ?array
{
    $path = sh_runtime_dir() . '/web_status.json';
    if (!is_readable($path)) {
        return null;
    }
    $data = json_decode((string) file_get_contents($path), true);
    return is_array($data) ? $data : null;
}

function sh_http_get(string $url, int $timeout = 15): array
{
    if (function_exists('curl_init')) {
        $ch = curl_init($url);
        curl_setopt_array($ch, array(
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_FOLLOWLOCATION => true,
            CURLOPT_CONNECTTIMEOUT => $timeout,
            CURLOPT_TIMEOUT => $timeout,
            CURLOPT_USERAGENT => 'ShionMusicBot-Dashboard/2.0',
        ));
        $body = curl_exec($ch);
        $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $err = curl_error($ch);
        curl_close($ch);
        return array('ok' => $body !== false, 'body' => (string) $body, 'code' => $code, 'error' => $err);
    }
    $ctx = stream_context_create(array('http' => array('timeout' => $timeout)));
    $body = @file_get_contents($url, false, $ctx);
    return array('ok' => $body !== false, 'body' => (string) $body, 'code' => $body !== false ? 200 : 0, 'error' => '');
}

function sh_h(string $text): string
{
    return htmlspecialchars($text, ENT_QUOTES, 'UTF-8');
}
