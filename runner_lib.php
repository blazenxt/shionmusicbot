<?php
/**
 * ShionMusicBot — shared runner helpers.
 *
 * Used by runner.php (process control) and the web dashboard pages.
 * Kept PHP 7.4+ compatible and free of external dependencies.
 */

declare(strict_types=1);

function sh_env(string $key, string $default = ''): string
{
    static $env = null;
    if ($env === null) {
        $env = array();
        $path = __DIR__ . '/.env';
        if (is_readable($path)) {
            $lines = file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            foreach ((array) $lines as $line) {
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
    $given = isset($_GET['key']) ? (string) $_GET['key']
        : (isset($_SERVER['HTTP_X_RUNNER_KEY']) ? (string) $_SERVER['HTTP_X_RUNNER_KEY'] : '');
    return $expected !== '' && $given !== '' && hash_equals($expected, $given);
}

function sh_run(string $cmd): string
{
    $out = @shell_exec($cmd . ' 2>&1');
    return is_string($out) ? $out : '';
}

function sh_bg(string $cmd, string $log): void
{
    $dir = escapeshellarg(__DIR__);
    $logPath = escapeshellarg(__DIR__ . '/' . ltrim($log, '/'));
    $full = 'export PATH=' . escapeshellarg(__DIR__ . '/bin') . ':$PATH; ' . $cmd;
    @shell_exec(
        sprintf(
            'cd %s && nohup bash -c %s >> %s 2>&1 < /dev/null &',
            $dir,
            escapeshellarg($full),
            $logPath
        )
    );
}

function sh_proc_running(): bool
{
    return trim(sh_run("pgrep -f -- '-m anony'")) !== '';
}

function sh_python(): string
{
    return is_file(__DIR__ . '/venv/bin/python3') ? __DIR__ . '/venv/bin/python3' : 'python3';
}

function sh_tail(string $file, int $lines = 80): array
{
    if (!is_readable($file)) {
        return array();
    }
    $all = file($file, FILE_IGNORE_NEW_LINES);
    if ($all === false) {
        return array();
    }
    return array_slice($all, -$lines);
}

function sh_web_status(): ?array
{
    $path = __DIR__ . '/web_status.json';
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
            CURLOPT_USERAGENT => 'ShionMusicBot-Dashboard/1.0',
        ));
        $body = curl_exec($ch);
        $code = (int) curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $err = curl_error($ch);
        curl_close($ch);
        return array('ok' => $body !== false, 'body' => (string) $body, 'code' => $code, 'error' => $err);
    }
    $ctx = stream_context_create(array('http' => array('timeout' => $timeout)));
    $body = @file_get_contents($url, false, $ctx);
    return array(
        'ok' => $body !== false,
        'body' => (string) $body,
        'code' => $body !== false ? 200 : 0,
        'error' => $body !== false ? '' : 'request failed',
    );
}

function sh_h(string $text): string
{
    return htmlspecialchars((string) $text, ENT_QUOTES, 'UTF-8');
}
