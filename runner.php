<?php
/**
 * ShionMusicBot — background daemon control endpoint.
 *
 * All actions require the RUNNER_KEY from .env:
 *   runner.php?key=…&action=diag      — server environment report
 *   runner.php?key=…&action=bootstrap — create venv + pip install + ffmpeg
 *   runner.php?key=…&action=start     — kill old process & start the bot
 *   runner.php?key=…&action=stop      — stop the bot
 *   runner.php?key=…&action=restart   — stop + start
 *   runner.php?key=…&action=ensure    — start only when not running
 *   runner.php?key=…&action=status    — quick status peek
 *   runner.php?key=…&action=log       — tail bot.log (file=install for install.log)
 */

declare(strict_types=1);

require __DIR__ . '/runner_lib.php';

header('Content-Type: text/plain; charset=utf-8');
header('X-Robots-Tag: noindex, nofollow');

if (!sh_key_ok()) {
    http_response_code(403);
    exit("Forbidden\n");
}

$action = isset($_GET['action']) ? (string) $_GET['action'] : 'status';
$dir = __DIR__;

switch ($action) {
    case 'diag':
        echo 'php: ', PHP_VERSION, ' ', php_sapi_name(), "\n";
        echo 'disable_functions: ', ini_get('disable_functions') ?: 'none', "\n";
        echo 'whoami: ', sh_run('whoami');
        echo 'python: ', sh_run(sh_python() . ' -V');
        echo 'venv: ', is_file($dir . '/venv/bin/python3') ? 'present' : 'absent', "\n";
        echo 'ffmpeg: ', sh_run(
            'export PATH=' . escapeshellarg($dir . '/bin') . ':$PATH; command -v ffmpeg; ffmpeg -version 2>/dev/null | head -1'
        );
        echo 'running: ', sh_proc_running() ? 'yes' : 'no', "\n";
        echo 'bootstrapped: ', is_file($dir . '/.bootstrapped') ? 'yes' : 'no', "\n";
        echo 'testweb3: ', trim(sh_run(
            "curl -s -m 12 -o /dev/null -w '%{http_code}' 'http://Testweb3.cstsc.in/yt/api.php?action=search&q=ping'"
        )), "\n";
        break;

    case 'bootstrap':
        sh_bg('bash bootstrap.sh', 'install.log');
        echo "bootstrap started — poll: action=log&file=install\n";
        break;

    case 'start':
    case 'restart':
        sh_run("pkill -f -- '-m anony'");
        usleep(900000);
        sh_bg(escapeshellarg(sh_python()) . ' -m anony', 'data/nohup.log');
        sleep(3);
        echo sh_proc_running() ? "started\n" : "FAILED — inspect action=log&file=bot\n";
        break;

    case 'stop':
        sh_run("pkill -f -- '-m anony'");
        sleep(1);
        echo sh_proc_running() ? "still running\n" : "stopped\n";
        break;

    case 'ensure':
        if (!sh_proc_running() && is_file($dir . '/.bootstrapped')) {
            sh_bg('bash ensure-running.sh', 'data/watchdog.log');
            sleep(3);
        }
        echo sh_proc_running() ? "running\n" : "not running\n";
        break;

    case 'status':
        echo sh_proc_running() ? "RUNNING" : "STOPPED", "\n";
        $st = sh_web_status();
        if ($st !== null) {
            echo 'bot: ', $st['bot'] ?? '?', ' | uptime: ', $st['uptime'] ?? 0, 's',
                 ' | streams: ', count((array) ($st['active_calls'] ?? array())),
                 ' | plays: ', $st['plays'] ?? 0, "\n";
        }
        break;

    case 'log':
        $file = (isset($_GET['file']) && $_GET['file'] === 'install') ? 'install.log' : 'bot.log';
        $lines = isset($_GET['lines']) ? max(10, min(400, (int) $_GET['lines'])) : 60;
        echo "── {$file} (last {$lines} lines) ──\n";
        foreach (sh_tail($dir . '/' . $file, $lines) as $line) {
            echo $line, "\n";
        }
        break;

    default:
        echo "actions: diag | bootstrap | start | stop | restart | ensure | status | log\n";
}
