<?php
/**
 * ShionMusicBot — live status & ping console.
 * Auto-refreshes every 15 s and self-heals the daemon (watchdog-on-pagehit).
 */

require_once __DIR__ . '/runner_lib.php';
require_once __DIR__ . '/inc/ui.php';

// ── watchdog on page hit: revive the daemon when it died ────────────
$proc = false;
if (function_exists('shell_exec')) {
    $proc = trim((string) shell_exec("pgrep -f -- '-m anony' 2>/dev/null")) !== '';
}
$st = sh_web_status();
$fresh = ($st !== null && (time() - (int) ($st['ts'] ?? 0)) < 90);
$running = $proc || $fresh;

if (!$running && is_file(__DIR__ . '/.bootstrapped') && function_exists('shell_exec')) {
    @shell_exec(
        'cd ' . escapeshellarg(__DIR__) . ' && nohup bash ensure-running.sh >> '
        . escapeshellarg(__DIR__ . '/data/watchdog.log') . ' 2>&1 &'
    );
    sleep(3);
    $proc = trim((string) shell_exec("pgrep -f -- '-m anony' 2>/dev/null")) !== '';
    $running = $proc;
}

$queues = is_array($st['queues'] ?? null) ? $st['queues'] : array();
$queued_total = 0;
foreach ($queues as $count) {
    $queued_total += (int) $count;
}

sh_header('status', 'Live Status', 'Daemon health, playback metrics and the bot log console.');
?>

<meta http-equiv="refresh" content="15">

<section class="row spread mb">
  <?php echo sh_badge($running, $running ? 'Daemon online' : 'Daemon offline'); ?>
  <?php if ($fresh) {
      echo sh_badge(true, 'Metrics fresh (' . sh_h(date('H:i:s', (int) $st['ts'])) . ')');
  } else {
      echo sh_badge(false, 'Metrics stale');
  } ?>
  <span class="muted mono">pid <?php echo sh_h((string) ($st['pid'] ?? '—')); ?></span>
</section>

<section class="grid g4 mb">
  <div class="card stat"><div class="num"><?php echo $fresh ? sh_uptime($st['uptime'] ?? 0) : '—'; ?></div><div class="lbl">Uptime</div></div>
  <div class="card stat"><div class="num"><?php echo $fresh ? count((array) ($st['active_calls'] ?? array())) : '—'; ?></div><div class="lbl">Active streams</div></div>
  <div class="card stat"><div class="num"><?php echo $fresh ? (int) ($st['plays'] ?? 0) : '—'; ?></div><div class="lbl">Tracks played</div></div>
  <div class="card stat"><div class="num"><?php echo $fresh ? $queued_total : '—'; ?></div><div class="lbl">Queued tracks</div></div>
</section>

<section class="grid g3 mb">
  <div class="card">
    <h3><?php echo sh_icon('bot', 16); ?> Telegram</h3>
    <div class="kv"><span class="k">Bot</span><span class="mono"><?php echo sh_h((string) ($st['bot'] ?? '@' . sh_env('BOT_USERNAME', 'ShionMusicBot'))); ?></span></div>
    <div class="kv"><span class="k">Assistant</span><span class="mono"><?php echo sh_h((string) ($st['assistant'] ?? '@' . sh_env('ASSISTANT_USERNAME', 'ShionVCAssistant'))); ?></span></div>
    <div class="kv"><span class="k">Chats / Users</span><span><?php echo $fresh ? (int) ($st['chats'] ?? 0) . ' / ' . (int) ($st['users'] ?? 0) : '—'; ?></span></div>
  </div>
  <div class="card">
    <h3><?php echo sh_icon('layers', 16); ?> Stack</h3>
    <div class="kv"><span class="k">Python</span><span class="mono"><?php echo sh_h((string) ($st['py'] ?? '—')); ?></span></div>
    <div class="kv"><span class="k">Pyrogram</span><span class="mono"><?php echo sh_h((string) ($st['pyrogram'] ?? '—')); ?></span></div>
    <div class="kv"><span class="k">PyTgCalls</span><span class="mono"><?php echo sh_h((string) ($st['pytgcalls'] ?? '—')); ?></span></div>
  </div>
  <div class="card">
    <h3><?php echo sh_icon('cpu', 16); ?> Resources</h3>
    <div class="kv"><span class="k">Process CPU</span><span><?php echo $fresh ? sh_h((string) ($st['cpu'] ?? '—')) . '%' : '—'; ?></span></div>
    <div class="kv"><span class="k">Process RAM</span><span><?php echo $fresh ? sh_h((string) ($st['mem_mb'] ?? '—')) . ' MB' : '—'; ?></span></div>
    <div class="kv"><span class="k">System RAM</span><span><?php echo $fresh ? sh_h((string) ($st['sys_mem'] ?? '—')) . '%' : '—'; ?></span></div>
  </div>
</section>

<?php if ($fresh && !empty($st['active_calls'])) { ?>
<section class="card mb">
  <h3><?php echo sh_icon('pulse', 16); ?> Active voice chats</h3>
  <div class="row">
    <?php foreach ((array) $st['active_calls'] as $chat) {
        echo '<span class="badge ok"><span class="dot ok"></span>chat ' . sh_h((string) $chat) . '</span>';
    } ?>
  </div>
</section>
<?php } ?>

<section class="card">
  <h3><?php echo sh_icon('terminal', 16); ?> bot.log console <span class="muted" style="font-weight:400">— last 80 lines, refresh 15 s</span></h3>
  <div class="console"><?php
    $lines = sh_tail(__DIR__ . '/bot.log', 80);
    if (!$lines) {
        echo 'no log output yet…';
    } else {
        foreach ($lines as $line) {
            $cls = '';
            if (strpos($line, '| ERROR') !== false || strpos($line, '| CRITICAL') !== false) {
                $cls = ' class="err"';
            } elseif (strpos($line, '| WARNING') !== false) {
                $cls = ' class="warn"';
            }
            echo '<span' . $cls . '>' . sh_h($line) . "</span>\n";
        }
    }
  ?></div>
</section>

<?php sh_footer(); ?>
