<?php
/** Key-protected daemon control endpoint. */
declare(strict_types=1);
require __DIR__ . '/runner_lib.php';

header('Content-Type: text/plain; charset=utf-8');
header('X-Robots-Tag: noindex, nofollow');
header('Cache-Control: no-store');

if (!sh_key_ok()) {
    http_response_code(403);
    exit("Forbidden\n");
}

$action = isset($_GET['action']) ? (string) $_GET['action'] : 'status';
$runtime = sh_runtime_dir();

switch ($action) {
    case 'diag':
        echo 'php: ', PHP_VERSION, ' ', php_sapi_name(), "\n";
        echo 'runtime: ', $runtime, "\n";
        echo 'python: ', sh_run(escapeshellarg(sh_python()) . ' -V');
        echo 'venv: ', is_file($runtime . '/venv/bin/python3') ? 'present' : 'absent', "\n";
        echo 'ffmpeg: ', sh_run('export PATH=' . escapeshellarg($runtime . '/bin') . ':$PATH; command -v ffmpeg; ffmpeg -version 2>/dev/null | head -1');
        echo 'running: ', sh_proc_running() ? 'yes' : 'no', "\n";
        echo 'pid: ', sh_pid() ?: 'none', "\n";
        echo 'bootstrapped: ', is_file($runtime . '/.bootstrapped') ? 'yes' : 'no', "\n";
        echo 'session_required: ', is_file($runtime . '/SESSION_REQUIRED') ? 'yes' : 'no', "\n";
        echo 'proc_open: ', function_exists('proc_open') ? 'enabled' : 'disabled', "\n";
        break;

    case 'bootstrap':
        @mkdir($runtime, 0700, true);
        $cmd = 'cd ' . escapeshellarg(__DIR__)
            . ' && export SHION_RUNTIME_DIR=' . escapeshellarg($runtime)
            . ' && nohup bash bootstrap.sh >> ' . escapeshellarg($runtime . '/install.log')
            . ' 2>&1 < /dev/null &';
        @shell_exec('bash -c ' . escapeshellarg($cmd));
        echo "bootstrap started\n";
        break;

    case 'start':
        echo sh_start_bot() ? "started\n" : "FAILED\n";
        break;

    case 'restart':
        echo sh_restart_bot() ? "restarted\n" : "FAILED\n";
        break;

    case 'stop':
        sh_stop_bot();
        echo sh_proc_running() ? "still running\n" : "stopped\n";
        break;

    case 'ensure':
        echo sh_start_bot() ? "running\n" : "not running\n";
        break;

    case 'status':
        echo sh_proc_running() ? "RUNNING" : "STOPPED", "\n";
        $st = sh_web_status();
        if ($st !== null) {
            echo 'bot: ', $st['bot'] ?? '?', ' | assistant: ', !empty($st['assistant_ready']) ? 'ready' : 'login required',
                 ' | uptime: ', $st['uptime'] ?? 0, 's | streams: ', count((array) ($st['active_calls'] ?? array())), "\n";
        }
        break;

    case 'log':
        $file = (isset($_GET['file']) && $_GET['file'] === 'install') ? 'install.log' : 'bot.log';
        $lines = isset($_GET['lines']) ? max(10, min(400, (int) $_GET['lines'])) : 60;
        echo "-- {$file} (last {$lines} lines) --\n";
        foreach (sh_tail($runtime . '/' . $file, $lines) as $line) {
            echo $line, "\n";
        }
        break;

    default:
        echo "actions: diag | bootstrap | start | stop | restart | ensure | status | log\n";
}
